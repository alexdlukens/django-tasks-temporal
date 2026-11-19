import uuid
from contextlib import suppress
from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.tasks import task_backends
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleIntervalSpec,
    ScheduleRange,
    ScheduleSpec,
    ScheduleState,
)
from temporalio.service import RPCError

from django_tasks_temporal._shared import WORKFLOW_NAME, TaskInput
from django_tasks_temporal.schedules import (
    MANAGED_MEMO_KEY,
    prune_schedules,
    sync_schedules,
)

EXPECTED_IDS = ["test-every-paused", "test-cron"]


def describe_schedule(schedule_id: str):
    async def run():
        client = await Client.connect(settings.TEMPORAL_TEST_ADDRESS)
        return await client.get_schedule_handle(schedule_id).describe()

    return async_to_sync(run)()


def _direct_schedule(schedule_id: str, memo: dict[str, str] | None = None) -> Schedule:
    """A schedule shaped like ours, but not created through sync."""
    return Schedule(
        action=ScheduleActionStartWorkflow(
            WORKFLOW_NAME,
            args=[
                TaskInput(
                    task_path="tests.app.tasks.scheduled_tick",
                    args=[],
                    kwargs={},
                )
            ],
            id=schedule_id,
            task_queue="default",
            memo=memo,
        ),
        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=5))]),
        state=ScheduleState(paused=True),
    )


def _create_directly_and_prune(
    schedule_id: str, memo: dict[str, str] | None
) -> list[str]:
    async def run() -> list[str]:
        client = await Client.connect(settings.TEMPORAL_TEST_ADDRESS)
        try:
            await client.create_schedule(
                schedule_id, _direct_schedule(schedule_id, memo)
            )
            pruned = await prune_schedules("scheduled", EXPECTED_IDS)
            # Still there: prune must not have deleted it.
            await client.get_schedule_handle(schedule_id).describe()
            return pruned
        finally:
            with suppress(RPCError):
                await client.get_schedule_handle(schedule_id).delete()

    return async_to_sync(run)()


def test_sync_creates_schedules_and_is_idempotent():
    assert async_to_sync(sync_schedules)("scheduled") == EXPECTED_IDS

    paused = describe_schedule("test-every-paused")
    assert paused.schedule.state.paused is True
    assert paused.schedule.spec.intervals[0].every == timedelta(hours=1)

    # A second sync hits the already-exists path and must update in place.
    assert async_to_sync(sync_schedules)("scheduled") == EXPECTED_IDS

    cron = describe_schedule("test-cron")
    # The server normalizes cron strings into calendar specs on describe.
    (calendar,) = cron.schedule.spec.calendars
    assert calendar.hour == (ScheduleRange(start=9, end=9, step=1),)
    assert calendar.minute == (ScheduleRange(start=0, end=0, step=1),)
    assert cron.schedule.state.paused is False


def test_sync_refuses_to_overwrite_another_aliases_schedule():
    backend = task_backends["scheduled"]
    original = backend.options["SCHEDULES"]
    schedule_id = f"test-conflict-{uuid.uuid4().hex}"

    async def run() -> None:
        client = await Client.connect(settings.TEMPORAL_TEST_ADDRESS)
        try:
            await client.create_schedule(
                schedule_id,
                _direct_schedule(schedule_id, {MANAGED_MEMO_KEY: "other"}),
            )
            backend.options["SCHEDULES"] = [
                {
                    "id": schedule_id,
                    "task": "tests.app.tasks.scheduled_tick",
                    "every": 3600,
                }
            ]
            with pytest.raises(ImproperlyConfigured, match="another backend"):
                await sync_schedules("scheduled")
        finally:
            backend.options["SCHEDULES"] = original
            with suppress(RPCError):
                await client.get_schedule_handle(schedule_id).delete()

    async_to_sync(run)()


def test_prune_deletes_managed_schedules_no_longer_declared():
    backend = task_backends["scheduled"]
    original = backend.options["SCHEDULES"]
    suffix = uuid.uuid4().hex
    kept_id = f"test-prune-keep-{suffix}"
    removed_id = f"test-prune-remove-{suffix}"
    protected = [entry["id"] for entry in original]

    def declared(*ids: str) -> list[dict[str, object]]:
        return [
            {"id": schedule_id, "task": "tests.app.tasks.scheduled_tick", "every": 3600}
            for schedule_id in ids
        ]

    async def run() -> list[str]:
        client = await Client.connect(settings.TEMPORAL_TEST_ADDRESS)
        try:
            backend.options["SCHEDULES"] = declared(kept_id, removed_id)
            assert await sync_schedules("scheduled") == [kept_id, removed_id]
            # The second sync updates in place; the marker must survive.
            assert await sync_schedules("scheduled") == [kept_id, removed_id]

            backend.options["SCHEDULES"] = declared(kept_id)
            pruned = await prune_schedules("scheduled", [kept_id, *protected])
            await client.get_schedule_handle(kept_id).describe()
            with pytest.raises(RPCError):
                await client.get_schedule_handle(removed_id).describe()
            return pruned
        finally:
            backend.options["SCHEDULES"] = original
            for schedule_id in (kept_id, removed_id):
                with suppress(RPCError):
                    await client.get_schedule_handle(schedule_id).delete()

    assert async_to_sync(run)() == [removed_id]


def test_prune_keeps_unmanaged_schedules():
    schedule_id = f"test-unmanaged-{uuid.uuid4().hex}"
    assert schedule_id not in _create_directly_and_prune(schedule_id, None)


def test_prune_keeps_schedules_owned_by_another_alias():
    schedule_id = f"test-other-alias-{uuid.uuid4().hex}"
    pruned = _create_directly_and_prune(schedule_id, {MANAGED_MEMO_KEY: "other"})
    assert schedule_id not in pruned
