"""Session-wide Temporal dev server and worker for the test suite.

The dev server is started on the port in ``TEMPORAL_TEST_ADDRESS`` (see
``tests/settings.py``). A single worker serves every queue of the default
backend on a private event loop in a background thread. Tests enqueue with
the synchronous Django API, which connects independently, so they never share
a loop with the worker.
"""

import asyncio
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from django.conf import settings
from temporalio.testing import WorkflowEnvironment


class _LoopThread:
    """Run coroutines on a private event loop in a daemon thread."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self._thread.start()

    def run(self, coro: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=120)

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=30)
        self.loop.close()


@pytest.fixture(scope="session")
def temporal_server() -> Iterator[None]:
    address = settings.TEMPORAL_TEST_ADDRESS
    port = address.rsplit(":", 1)[1]
    runner = _LoopThread()
    env = runner.run(WorkflowEnvironment.start_local(port=int(port)))
    try:
        yield
    finally:
        runner.run(env.shutdown())
        runner.close()


@pytest.fixture(scope="session", autouse=True)
def temporal_worker(temporal_server: None) -> Iterator[None]:
    # Imported here, not at module level, so Django is configured first.
    from django_tasks_temporal.worker import run_workers
    from tests.app import workflows  # noqa: F401  (registers AddTwiceWorkflow)

    async def start() -> "asyncio.Task[None]":
        return asyncio.create_task(run_workers("default"))

    async def stop(task: "asyncio.Task[None]") -> None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    runner = _LoopThread()
    task = runner.run(start())
    try:
        yield
    finally:
        runner.run(stop(task))
        runner.close()
