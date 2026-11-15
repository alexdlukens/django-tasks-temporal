"""Create or update the Temporal Schedules configured for a Django backend."""

from __future__ import annotations

import asyncio
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from ..._shared import DEFAULT_BACKEND_ALIAS
from ...schedules import prune_schedules, sync_schedules


class Command(BaseCommand):
    help = (
        "Create or update the Temporal Schedules declared in the selected "
        "Django tasks backend's SCHEDULES option."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--backend",
            default=DEFAULT_BACKEND_ALIAS,
            help=(
                "Django tasks backend alias whose SCHEDULES to sync "
                f"(default: {DEFAULT_BACKEND_ALIAS})."
            ),
        )
        parser.add_argument(
            "--prune",
            action="store_true",
            help=(
                "Delete Temporal Schedules this backend previously created for "
                "the selected alias that are no longer declared in SCHEDULES."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        alias = options["backend"]
        synced = asyncio.run(sync_schedules(alias))
        for schedule_id in synced:
            self.stdout.write(schedule_id)

        if not options["prune"]:
            return
        for schedule_id in asyncio.run(prune_schedules(alias, synced)):
            self.stdout.write(f"pruned {schedule_id}")
