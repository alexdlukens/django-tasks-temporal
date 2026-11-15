"""Run Temporal workers that execute Django tasks."""

from __future__ import annotations

import asyncio
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from ..._shared import DEFAULT_BACKEND_ALIAS
from ...worker import discover, run_workers


class Command(BaseCommand):
    help = "Run Temporal workers processing Django tasks."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--backend",
            default=DEFAULT_BACKEND_ALIAS,
            help="Django task backend alias to serve (default: %(default)s).",
        )
        parser.add_argument(
            "--queue",
            action="append",
            dest="queues",
            metavar="QUEUE",
            help=(
                "Temporal task queue to serve; may be repeated. "
                "Defaults to the backend's QUEUES setting."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        discover()
        try:
            asyncio.run(run_workers(options["backend"], options["queues"]))
        except KeyboardInterrupt:
            # Ctrl-C already triggered a graceful worker shutdown.
            pass
