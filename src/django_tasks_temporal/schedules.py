"""Temporal Schedules driven by Django task backend configuration.

A schedule entry in ``TASKS[alias]["OPTIONS"]["SCHEDULES"]`` describes a Django
task that Temporal should start on a cron expression or a fixed interval. Each
entry maps to exactly one Temporal Schedule whose action starts
``DjangoTaskWorkflow`` with the task's ``TaskInput``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.tasks import Task, task_backends
from django.utils.module_loading import import_string
from temporalio.api.common.v1 import Payload
from temporalio.client import (
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleListActionStartWorkflow,
    ScheduleSpec,
    ScheduleState,
    ScheduleUpdate,
    ScheduleUpdateInput,
)
from temporalio.common import Priority

from ._shared import WORKFLOW_NAME, TaskInput, temporal_priority_key
from .client import connect, get_activity_timeout, get_options

# Memo key put on a managed schedule's start-workflow action, holding the
# backend alias that owns it. Pruning only deletes schedules carrying this
# marker for the alias being synced.
MANAGED_MEMO_KEY = "django_tasks_temporal"

_ALLOWED_KEYS = frozenset({"id", "task", "cron", "every", "args", "kwargs", "paused"})
_REQUIRED_KEYS = frozenset({"id", "task"})


@dataclass(frozen=True, slots=True)
class ScheduleConfig:
    """Validated schedule entry from the backend's ``SCHEDULES`` option."""

    id: str
    task_path: str
    cron: str | None
    every: timedelta | None
    args: list[Any]
    kwargs: dict[str, Any]
    paused: bool


def _invalid(alias: str, index: int, message: str) -> ImproperlyConfigured:
    return ImproperlyConfigured(
        f"TASKS[{alias!r}]['OPTIONS']['SCHEDULES'][{index}]: {message}"
    )


def _parse_entry(alias: str, index: int, entry: Any) -> ScheduleConfig:
    if not isinstance(entry, dict):
        raise _invalid(alias, index, "each schedule must be a mapping.")

    unknown = set(entry) - _ALLOWED_KEYS
    if unknown:
        names = ", ".join(sorted(map(repr, unknown)))
        raise _invalid(alias, index, f"unknown key(s): {names}.")

    missing = _REQUIRED_KEYS - set(entry)
    if missing:
        names = ", ".join(sorted(missing))
        raise _invalid(alias, index, f"missing required key(s): {names}.")

    schedule_id = entry["id"]
    if not isinstance(schedule_id, str) or not schedule_id:
        raise _invalid(alias, index, "'id' must be a non-empty string.")

    task_path = entry["task"]
    if not isinstance(task_path, str) or not task_path:
        raise _invalid(alias, index, "'task' must be a dotted path string.")

    has_cron = "cron" in entry
    has_every = "every" in entry
    if has_cron and has_every:
        raise _invalid(alias, index, "specify exactly one of 'cron' or 'every'.")
    if not has_cron and not has_every:
        raise _invalid(alias, index, "specify exactly one of 'cron' or 'every'.")

    cron: str | None = None
    every: timedelta | None = None
    if has_cron:
        cron = entry["cron"]
        if not isinstance(cron, str) or not cron:
            raise _invalid(alias, index, "'cron' must be a non-empty string.")
    else:
        raw_every = entry["every"]
        if isinstance(raw_every, bool) or not isinstance(raw_every, (timedelta, int)):
            raise _invalid(alias, index, "'every' must be a timedelta or int seconds.")
        every = (
            raw_every
            if isinstance(raw_every, timedelta)
            else timedelta(seconds=raw_every)
        )
        if every <= timedelta(0):
            raise _invalid(alias, index, "'every' must be positive.")

    args = entry.get("args", [])
    if not isinstance(args, list):
        raise _invalid(alias, index, "'args' must be a list.")

    kwargs = entry.get("kwargs", {})
    if not isinstance(kwargs, dict):
        raise _invalid(alias, index, "'kwargs' must be a dict.")

    paused = entry.get("paused", False)
    if not isinstance(paused, bool):
        raise _invalid(alias, index, "'paused' must be a bool.")

    return ScheduleConfig(
        id=schedule_id,
        task_path=task_path,
        cron=cron,
        every=every,
        args=list(args),
        kwargs=dict(kwargs),
        paused=paused,
    )


def parse_schedules(alias: str) -> list[ScheduleConfig]:
    """Validate and return the schedules configured for ``alias``."""
    raw = task_backends[alias].options.get("SCHEDULES", [])
    if not isinstance(raw, (list, tuple)):
        raise ImproperlyConfigured(
            f"TASKS[{alias!r}]['OPTIONS']['SCHEDULES'] must be a list."
        )

    configs: list[ScheduleConfig] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        config = _parse_entry(alias, index, entry)
        if config.id in seen:
            raise _invalid(alias, index, f"duplicate schedule id {config.id!r}.")
        seen.add(config.id)
        configs.append(config)
    return configs


def _replacing(schedule: Schedule) -> Callable[[ScheduleUpdateInput], ScheduleUpdate]:
    """Build an update callback that swaps in ``schedule`` wholesale."""

    def update(_input: ScheduleUpdateInput) -> ScheduleUpdate:
        return ScheduleUpdate(schedule=schedule)

    return update


def _build_schedule(
    task: Task, config: ScheduleConfig, alias: str, activity_timeout_seconds: float
) -> Schedule:
    if config.cron is not None:
        spec = ScheduleSpec(cron_expressions=[config.cron])
    else:
        assert config.every is not None
        spec = ScheduleSpec(intervals=[ScheduleIntervalSpec(every=config.every)])
    action = ScheduleActionStartWorkflow(
        WORKFLOW_NAME,
        args=[
            TaskInput(
                task_path=config.task_path,
                args=list(config.args),
                kwargs=dict(config.kwargs),
                activity_timeout_seconds=activity_timeout_seconds,
            )
        ],
        id=config.id,
        task_queue=task.queue_name,
        memo={MANAGED_MEMO_KEY: alias},
        priority=Priority(priority_key=temporal_priority_key(task.priority)),
    )
    return Schedule(
        action=action,
        spec=spec,
        state=ScheduleState(paused=config.paused),
    )


async def sync_schedules(alias: str) -> list[str]:
    """Create or update the Temporal Schedules configured for ``alias``.

    Returns the ids of the schedules that were synced, in configuration order.
    """
    configs = parse_schedules(alias)
    if not configs:
        return []

    # Resolve and validate every task before touching the network so that a
    # configuration error fails without needing a Temporal server.
    tasks: list[Task] = []
    for config in configs:
        task = import_string(config.task_path)
        if not isinstance(task, Task):
            raise ImproperlyConfigured(
                f"TASKS[{alias!r}]['OPTIONS']['SCHEDULES']: "
                f"{config.task_path!r} is not a Django task."
            )
        if task.backend != alias:
            raise ImproperlyConfigured(
                f"TASKS[{alias!r}]['OPTIONS']['SCHEDULES']: task "
                f"{config.task_path!r} uses backend {task.backend!r}."
            )
        tasks.append(task)

    activity_timeout_seconds = get_activity_timeout(alias)
    client = await connect(get_options(alias))
    synced: list[str] = []
    for config, task in zip(configs, tasks, strict=True):
        schedule = _build_schedule(task, config, alias, activity_timeout_seconds)
        try:
            await client.create_schedule(config.id, schedule)
        except ScheduleAlreadyRunningError:
            handle = client.get_schedule_handle(config.id)
            await handle.update(_replacing(schedule))
        synced.append(config.id)
    return synced


async def prune_schedules(alias: str, keep_ids: Iterable[str]) -> list[str]:
    """Delete Schedules managed by ``alias`` that are not in ``keep_ids``.

    Only schedules whose action starts ``DjangoTaskWorkflow`` and whose action
    memo carries ``MANAGED_MEMO_KEY`` set to ``alias`` are considered, so
    schedules owned by other backend aliases, and schedules created before the
    marker existed, are left alone. Returns the deleted ids.
    """
    keep = set(keep_ids)
    client = await connect(get_options(alias))
    pruned: list[str] = []
    async for entry in await client.list_schedules():
        if entry.id in keep:
            continue
        listed = entry.schedule
        if (
            listed is None
            or not isinstance(listed.action, ScheduleListActionStartWorkflow)
            or listed.action.workflow != WORKFLOW_NAME
        ):
            continue

        description = await client.get_schedule_handle(entry.id).describe()
        action = description.schedule.action
        if not isinstance(action, ScheduleActionStartWorkflow):
            continue
        memo = action.memo
        payload = memo.get(MANAGED_MEMO_KEY) if memo else None
        # describe() exposes the action memo as raw payloads.
        if not isinstance(payload, Payload):
            continue
        owner = (await description.data_converter.decode([payload]))[0]
        if owner != alias:
            continue

        await client.get_schedule_handle(entry.id).delete()
        pruned.append(entry.id)
    return pruned
