"""Django task backend that runs tasks as Temporal workflow executions."""

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from asgiref.sync import async_to_sync
from django.tasks import Task, TaskResult, TaskResultStatus
from django.tasks.backends.base import BaseTaskBackend
from django.utils import timezone
from temporalio.common import Priority

from . import client
from ._shared import TaskInput, temporal_priority_key
from .results import fetch_task_result
from .workflows import DjangoTaskWorkflow


def _start_delay(run_after: datetime | None) -> timedelta | None:
    """Return the Temporal start delay for ``run_after``, if it is in the future."""
    if run_after is None:
        return None
    now = datetime.now(UTC) if timezone.is_aware(run_after) else datetime.now()
    delay = run_after - now
    return delay if delay > timedelta(0) else None


class TemporalTaskBackend(BaseTaskBackend):
    """Run Django tasks on Temporal, one workflow execution per task execution."""

    supports_defer = True
    supports_async_task = True
    supports_get_result = True
    supports_priority = True

    def enqueue(
        self, task: Task, args: Sequence[Any], kwargs: Mapping[str, Any]
    ) -> TaskResult:
        return async_to_sync(self.aenqueue)(task, args, kwargs)

    async def aenqueue(
        self, task: Task, args: Sequence[Any], kwargs: Mapping[str, Any]
    ) -> TaskResult:
        temporal = await client.connect(client.get_options(self.alias))
        result_id = uuid.uuid4().hex
        await temporal.start_workflow(
            DjangoTaskWorkflow.run,
            TaskInput(
                task.module_path,
                list(args),
                dict(kwargs),
                activity_timeout_seconds=client.get_activity_timeout(self.alias),
            ),
            id=result_id,
            task_queue=task.queue_name,
            start_delay=_start_delay(task.run_after),
            priority=Priority(priority_key=temporal_priority_key(task.priority)),
        )
        return TaskResult(
            task=task,
            id=result_id,
            status=TaskResultStatus.READY,
            enqueued_at=timezone.now(),
            started_at=None,
            finished_at=None,
            last_attempted_at=None,
            args=list(args),
            kwargs=dict(kwargs),
            backend=self.alias,
            errors=[],
            worker_ids=[],
        )

    def get_result(self, result_id: str) -> TaskResult:
        return async_to_sync(self.aget_result)(result_id)

    async def aget_result(self, result_id: str) -> TaskResult:
        temporal = await client.connect(client.get_options(self.alias))
        return await fetch_task_result(temporal, self.alias, result_id)
