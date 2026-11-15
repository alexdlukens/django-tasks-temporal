import time
import uuid
from datetime import timedelta

from asgiref.sync import async_to_sync
from django.conf import settings
from django.tasks import TaskResult, TaskResultStatus, task_backends
from django.tasks.exceptions import TaskResultDoesNotExist
from django.utils import timezone
from temporalio.client import Client

from django_tasks_temporal._shared import temporal_priority_key
from tests.app.tasks import add, boom, result_id
from tests.app.workflows import AddTwiceWorkflow


def wait_for(
    result: TaskResult, status: TaskResultStatus, timeout: float = 30
) -> TaskResult:
    """Poll the backend until ``result`` reaches ``status``."""
    deadline = time.monotonic() + timeout
    backend = task_backends[result.backend]
    while True:
        current = backend.get_result(result.id)
        if current.status == status:
            return current
        if time.monotonic() > deadline:
            raise AssertionError(
                f"Task {result.id} stayed {current.status} (wanted {status})."
            )
        time.sleep(0.2)


def test_enqueued_task_runs_and_returns_value():
    result = add.enqueue(2, 3)

    done = wait_for(result, TaskResultStatus.SUCCESSFUL)

    assert done.return_value == 5
    assert done.args == [2, 3]


def test_failed_task_records_error_without_raising():
    result = boom.enqueue("bad input")

    done = wait_for(result, TaskResultStatus.FAILED)

    assert len(done.errors) == 1
    assert done.errors[0].exception_class_path == "builtins.ValueError"
    assert "bad input" in done.errors[0].traceback


def test_takes_context_task_receives_its_result_id():
    result = result_id.enqueue()

    done = wait_for(result, TaskResultStatus.SUCCESSFUL)

    assert done.return_value == result.id


def test_unknown_result_id_raises_does_not_exist():
    backend = task_backends["default"]

    try:
        backend.get_result(uuid.uuid4().hex)
    except TaskResultDoesNotExist:
        return
    raise AssertionError("get_result did not raise TaskResultDoesNotExist")


def test_deferred_task_is_ready_until_run_after_then_runs():
    run_after = timezone.now() + timedelta(seconds=2)

    result = add.using(run_after=run_after).enqueue(1, 1)

    assert result.status == TaskResultStatus.READY
    done = wait_for(result, TaskResultStatus.SUCCESSFUL, timeout=60)
    assert done.return_value == 2


def test_user_workflow_runs_django_tasks_as_activities():
    async def run() -> int:
        client = await Client.connect(settings.TEMPORAL_TEST_ADDRESS)
        return await client.execute_workflow(
            AddTwiceWorkflow.run,
            args=[1, 2],
            id=f"add-twice-{uuid.uuid4().hex}",
            task_queue="default",
        )

    assert async_to_sync(run)() == 5


def test_higher_django_priority_maps_to_lower_temporal_key():
    keys = [temporal_priority_key(priority) for priority in (100, 0, -100)]

    assert keys == sorted(keys)
    assert keys[0] < keys[-1]
