"""Worker process management: discovery, worker construction, and serving."""

from __future__ import annotations

import asyncio

from django.core.exceptions import ImproperlyConfigured
from django.tasks import task_backends
from django.utils.module_loading import autodiscover_modules
from temporalio.client import Client
from temporalio.worker import Worker

from .client import connect, get_options
from .workflows import DjangoTaskWorkflow, registered_workflows, run_task


def discover() -> None:
    """Import every installed app's ``tasks`` module.

    Importing those modules registers their Django tasks and any Temporal
    workflows decorated with :py:func:`django_tasks_temporal.workflows.workflow`.
    """
    autodiscover_modules("tasks")


def create_worker(client: Client, queue_name: str) -> Worker:
    """Build a worker serving the Django task workflow/activity on ``queue_name``."""
    return Worker(
        client,
        task_queue=queue_name,
        workflows=[DjangoTaskWorkflow, *registered_workflows()],
        activities=[run_task],
    )


async def _shutdown(workers: list[Worker]) -> None:
    await asyncio.gather(
        *(worker.shutdown() for worker in workers), return_exceptions=True
    )


async def run_workers(alias: str, queues: list[str] | None = None) -> None:
    """Serve Django tasks on one Temporal worker per queue until cancelled.

    ``queues`` defaults to the backend's ``QUEUES`` setting.
    """
    backend = task_backends[alias]
    queue_names = list(queues) if queues else sorted(backend.queues)
    if not queue_names:
        raise ImproperlyConfigured(
            f"Django task backend {alias!r} has no queues configured; "
            "set QUEUES or pass --queue."
        )

    client = await connect(get_options(alias))
    workers = [create_worker(client, queue_name) for queue_name in queue_names]
    run_tasks = [asyncio.create_task(worker.run()) for worker in workers]

    try:
        # Returns when a worker fails fatally or when every worker stops.
        await asyncio.wait(run_tasks, return_when=asyncio.FIRST_EXCEPTION)
    except BaseException:
        # Our own cancellation (e.g. Ctrl-C): shut down gracefully so in-flight
        # activities are allowed to finish before the cancellation propagates.
        await _shutdown(workers)
        await asyncio.gather(*run_tasks, return_exceptions=True)
        raise

    await _shutdown(workers)
    await asyncio.gather(*run_tasks, return_exceptions=True)
    for run_task_handle in run_tasks:
        if run_task_handle.cancelled():
            continue
        run_error = run_task_handle.exception()
        if run_error is not None:
            raise run_error
