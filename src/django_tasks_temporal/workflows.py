"""Temporal workflow and activity that execute a single Django task.

The workflow and activity defined here are the only pieces of this package
that run inside the Temporal workflow sandbox and inside Temporal activities.
Everything Django-related is imported through
:py:func:`temporalio.workflow.unsafe.imports_passed_through` so the sandbox
reuses the parent process's Django modules instead of reloading Django.

Users write their own Temporal workflows with the :py:func:`workflow`
decorator so the workers started by this package know about them:

    from temporalio import workflow as temporal
    from django_tasks_temporal.workflows import execute_task, workflow

    @workflow
    class SendReportsWorkflow:
        @temporal.run
        async def run(self) -> None:
            await execute_task(send_report)
"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from datetime import timedelta
from typing import Any, overload

from temporalio import activity
from temporalio import workflow as temporal_workflow
from temporalio.common import Priority, RetryPolicy
from temporalio.exceptions import ApplicationError
from temporalio.types import ClassType

from ._shared import (
    ACTIVITY_NAME,
    DEFAULT_ACTIVITY_TIMEOUT_SECONDS,
    WORKFLOW_NAME,
    TaskInput,
    temporal_priority_key,
)

# Django imports must be visible to the workflow sandbox as pass-through
# imports, otherwise the sandbox would fail while (re)importing this module.
with temporal_workflow.unsafe.imports_passed_through():
    from django.tasks import Task as DjangoTask
    from django.tasks import TaskContext, TaskResult, TaskResultStatus
    from django.utils.module_loading import import_string

#: Start-to-close timeout for activities that user workflows start with
#: :py:func:`execute_task`. Enqueued and scheduled tasks use the timeout carried
#: in their ``TaskInput`` instead, set by the backend's ``ACTIVITY_TIMEOUT``.
DEFAULT_ACTIVITY_TIMEOUT = timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS)

_REGISTERED_WORKFLOWS: list[type] = []


@overload
def workflow(cls: ClassType) -> ClassType: ...


@overload
def workflow(
    cls: None = None, *, name: str | None = None
) -> Callable[[ClassType], ClassType]: ...


def workflow(
    cls: ClassType | None = None, *, name: str | None = None
) -> ClassType | Callable[[ClassType], ClassType]:
    """Register a Temporal workflow class so the workers can serve it.

    Usable bare (``@workflow``) or with arguments (``@workflow(name="...")``).
    Applies :py:func:`temporalio.workflow.defn` and records the class in the
    registry read by :py:func:`registered_workflows`.
    """

    def decorator(user_cls: ClassType) -> ClassType:
        decorated = temporal_workflow.defn(name=name)(user_cls)
        if decorated not in _REGISTERED_WORKFLOWS:
            _REGISTERED_WORKFLOWS.append(decorated)
        return decorated

    if cls is not None:
        return decorator(cls)
    return decorator


def registered_workflows() -> list[type]:
    """Return the workflow classes registered with :py:func:`workflow`."""
    return list(_REGISTERED_WORKFLOWS)


@activity.defn(name=ACTIVITY_NAME)
async def run_task(task_input: TaskInput) -> Any:
    """Execute a Django task in an activity.

    Any exception is re-raised as an :py:class:`temporalio.exceptions.ApplicationError`
    carrying the exception class path as the error type and the formatted
    traceback as its first detail, which is how the backend rebuilds
    ``TaskError`` objects for failed task results.
    """
    info = activity.info()
    args = list(task_input.args)
    kwargs = dict(task_input.kwargs)

    try:
        task: DjangoTask = import_string(task_input.task_path)
        if task.takes_context:
            # Django tasks only ever get a single attempt here (the workflow
            # sets maximum_attempts=1), but synthesize the worker ids from the
            # activity attempt so TaskContext.attempt stays accurate if an
            # activity is retried manually from the Temporal UI/CLI.
            attempt = info.attempt
            task_result = TaskResult(
                task=task,
                # The workflow id is the Django task result id by construction.
                id=info.workflow_id or info.activity_id,
                status=TaskResultStatus.RUNNING,
                enqueued_at=info.scheduled_time,
                started_at=info.started_time,
                finished_at=None,
                last_attempted_at=info.started_time,
                args=args,
                kwargs=kwargs,
                backend=task.backend,
                errors=[],
                worker_ids=[f"attempt-{i}" for i in range(1, attempt + 1)],
            )
            return await task.acall(
                TaskContext(task_result=task_result), *args, **kwargs
            )
        return await task.acall(*args, **kwargs)
    except Exception as exc:
        raise ApplicationError(
            str(exc),
            traceback.format_exc(),
            type=f"{type(exc).__module__}.{type(exc).__qualname__}",
        ) from exc


@temporal_workflow.defn(name=WORKFLOW_NAME)
class DjangoTaskWorkflow:
    """Workflow execution representing exactly one Django task enqueue."""

    @temporal_workflow.run
    async def run(self, task_input: TaskInput) -> Any:
        return await temporal_workflow.execute_activity(
            ACTIVITY_NAME,
            task_input,
            start_to_close_timeout=timedelta(
                seconds=task_input.activity_timeout_seconds
            ),
            # Django has no automatic retry semantics; Temporal's default is
            # unlimited retries, so opt out explicitly.
            retry_policy=RetryPolicy(maximum_attempts=1),
        )


async def execute_task(task: DjangoTask, *args: Any, **kwargs: Any) -> Any:
    """Execute a Django task from inside a Temporal workflow.

    ``task`` must be a module-level Task instance so its ``module_path`` can be
    resolved by the activity with ``import_string``.
    """
    return await temporal_workflow.execute_activity(
        ACTIVITY_NAME,
        TaskInput(task.module_path, list(args), kwargs),
        task_queue=task.queue_name,
        priority=Priority(priority_key=temporal_priority_key(task.priority)),
        start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
        retry_policy=RetryPolicy(maximum_attempts=1),
    )
