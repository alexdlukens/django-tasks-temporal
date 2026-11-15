"""Rebuild Django ``TaskResult`` objects from Temporal workflow executions.

One Django task execution is one Temporal workflow execution whose id is the
``TaskResult`` id, so a result lookup is a describe plus (for the arguments) a
history read of the first event.
"""

import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import temporalio.api.history.v1
import temporalio.api.workflow.v1
import temporalio.client
from django.tasks import TaskResult, TaskResultStatus
from django.tasks.base import TaskError
from django.tasks.exceptions import TaskResultDoesNotExist
from django.utils.module_loading import import_string
from google.protobuf.timestamp_pb2 import Timestamp
from temporalio.client import WorkflowExecutionStatus, WorkflowFailureError
from temporalio.converter import DataConverter
from temporalio.exceptions import ApplicationError
from temporalio.service import RPCError, RPCStatusCode

from ._shared import TaskInput

_FAILED_STATUSES = frozenset(
    {
        WorkflowExecutionStatus.FAILED,
        WorkflowExecutionStatus.CANCELED,
        WorkflowExecutionStatus.TERMINATED,
        WorkflowExecutionStatus.TIMED_OUT,
    }
)


@dataclass(frozen=True, slots=True)
class _ActivityAttempts:
    """Activity attempt data derived from a workflow execution."""

    count: int
    started_at: datetime | None
    last_attempted_at: datetime | None
    worker_ids: list[str]


def _to_datetime(timestamp: Timestamp) -> datetime:
    return timestamp.ToDatetime().replace(tzinfo=UTC)


async def fetch_task_result(
    client: temporalio.client.Client, alias: str, result_id: str
) -> TaskResult:
    """Return the ``TaskResult`` for the Temporal workflow execution ``result_id``.

    Raises ``TaskResultDoesNotExist`` if no such execution exists.
    """
    handle = client.get_workflow_handle(result_id)
    try:
        description = await handle.describe()
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            raise TaskResultDoesNotExist(
                f"No task result with id {result_id!r}."
            ) from exc
        raise

    history = await handle.fetch_history()
    task_input = await _read_task_input(history, description.data_converter)
    attempts = _activity_attempts(
        history.events, description.raw_description.pending_activities
    )
    status = _map_status(description.status, attempts.count)

    errors: list[TaskError] = []
    return_value = None
    if status == TaskResultStatus.SUCCESSFUL:
        return_value = await handle.result()
    elif status == TaskResultStatus.FAILED:
        try:
            await handle.result()
        except WorkflowFailureError as exc:
            errors.append(_task_error(exc))

    result = TaskResult(
        task=import_string(task_input.task_path),
        id=result_id,
        status=status,
        enqueued_at=description.start_time,
        started_at=attempts.started_at,
        finished_at=description.close_time,
        last_attempted_at=attempts.last_attempted_at,
        args=list(task_input.args),
        kwargs=dict(task_input.kwargs),
        backend=alias,
        errors=errors,
        worker_ids=attempts.worker_ids,
    )
    if status == TaskResultStatus.SUCCESSFUL:
        object.__setattr__(result, "_return_value", return_value)
    return result


async def _read_task_input(
    history: temporalio.client.WorkflowHistory, data_converter: DataConverter
) -> TaskInput:
    """Decode the single workflow argument from the first history event."""
    for event in history.events:
        if not event.HasField("workflow_execution_started_event_attributes"):
            continue
        attributes = event.workflow_execution_started_event_attributes
        decoded = await data_converter.decode_wrapper(attributes.input, [TaskInput])
        if decoded and isinstance(decoded[0], TaskInput):
            return decoded[0]
        break
    raise RuntimeError(
        f"Workflow {history.workflow_id!r} has no {TaskInput.__name__} argument in "
        "its history; it was not started by the Temporal task backend."
    )


def _map_status(
    status: WorkflowExecutionStatus | None, attempts: int
) -> TaskResultStatus:
    """Map a Temporal workflow status to a Django task result status."""
    if status == WorkflowExecutionStatus.COMPLETED:
        return TaskResultStatus.SUCCESSFUL
    if status in _FAILED_STATUSES:
        return TaskResultStatus.FAILED
    if status == WorkflowExecutionStatus.RUNNING and attempts == 0:
        # The workflow exists but its activity has not been picked up yet.
        return TaskResultStatus.READY
    # RUNNING with a started activity, CONTINUED_AS_NEW, and unknown statuses.
    return TaskResultStatus.RUNNING


def _activity_attempts(
    events: Sequence[temporalio.api.history.v1.HistoryEvent],
    pending_activities: Sequence[temporalio.api.workflow.v1.PendingActivityInfo],
) -> _ActivityAttempts:
    """Derive attempt times and worker identities from history and pending state.

    Attempts seen in history carry the worker identity in the started event;
    an attempt that the server reports as started but which has no history event
    yet contributes its last worker identity, or ``attempt-<n>`` when the
    server has not recorded one.
    """
    started: list[tuple[datetime, str]] = []
    for event in events:
        if not event.HasField("activity_task_started_event_attributes"):
            continue
        attributes = event.activity_task_started_event_attributes
        started.append((_to_datetime(event.event_time), attributes.identity))

    pending_started = {
        activity.attempt: activity
        for activity in pending_activities
        if activity.attempt > 0 and activity.HasField("last_started_time")
    }
    count = max(len(started), max(pending_started, default=0))

    worker_ids = [
        identity or f"attempt-{attempt}"
        for attempt, (_, identity) in enumerate(started, start=1)
    ]
    for attempt in range(len(started) + 1, count + 1):
        pending = pending_started[attempt]
        worker_ids.append(pending.last_worker_identity or f"attempt-{attempt}")

    latest_pending = (
        _to_datetime(pending_started[max(pending_started)].last_started_time)
        if pending_started
        else None
    )
    first_pending = (
        _to_datetime(pending_started[1].last_started_time)
        if 1 in pending_started
        else None
    )
    return _ActivityAttempts(
        count=count,
        started_at=started[0][0] if started else first_pending,
        last_attempted_at=started[-1][0] if started else latest_pending,
        worker_ids=worker_ids,
    )


def _task_error(error: WorkflowFailureError) -> TaskError:
    """Convert a failed workflow's failure chain into a Django ``TaskError``."""
    current: BaseException | None = error
    deepest: BaseException = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ApplicationError):
            traceback_text = next(
                (
                    detail
                    for detail in current.details
                    if isinstance(detail, str) and detail
                ),
                "",
            )
            return TaskError(
                exception_class_path=current.type
                or f"{type(current).__module__}.{type(current).__qualname__}",
                traceback=traceback_text
                or "".join(traceback.format_exception(current)),
            )
        deepest = current
        current = current.__cause__

    return TaskError(
        exception_class_path=f"{type(deepest).__module__}.{type(deepest).__qualname__}",
        traceback="".join(traceback.format_exception(deepest)),
    )
