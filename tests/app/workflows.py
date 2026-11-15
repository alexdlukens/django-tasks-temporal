from temporalio import workflow

from django_tasks_temporal.workflows import execute_task
from django_tasks_temporal.workflows import workflow as temporal_workflow

with workflow.unsafe.imports_passed_through():
    from tests.app.tasks import add


@temporal_workflow
class AddTwiceWorkflow:
    @workflow.run
    async def run(self, a: int, b: int) -> int:
        first = await execute_task(add, a, b)
        return await execute_task(add, first, b)
