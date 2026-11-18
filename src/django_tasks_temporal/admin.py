"""Optional Django admin overview of Temporal workflow executions and schedules.

The page is registered through admin autodiscovery, so it appears only when
``django.contrib.admin`` is installed. Every Temporal task backend alias is
listed with its recent workflow executions and schedules. When an alias sets
``WEB_UI_URL`` in its ``TASKS`` options, rows and the alias header link to the
Temporal Web UI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import quote

import temporalio.client
from asgiref.sync import async_to_sync
from django.contrib import admin
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.tasks import task_backends
from django.template.response import TemplateResponse

from .backend import TemporalTaskBackend
from .client import TemporalOptions, connect, get_options
from .models import TemporalOverview
from .schedules import ScheduleConfig, parse_schedules

logger = logging.getLogger(__name__)

# Upper bounds for one admin page load.
WORKFLOW_LIMIT = 50
SCHEDULE_LIMIT = 50


@dataclass(frozen=True, slots=True)
class WorkflowRow:
    id: str
    workflow_type: str
    status: str
    task_queue: str
    start_time: datetime
    close_time: datetime | None
    url: str | None


@dataclass(frozen=True, slots=True)
class ScheduleRow:
    id: str
    task: str | None
    cadence: str | None
    paused: bool | None
    next_action_time: datetime | None
    url: str | None


@dataclass(frozen=True, slots=True)
class AliasOverview:
    alias: str
    namespace: str
    web_ui_url: str | None
    error: str | None = None
    workflows: list[WorkflowRow] = field(default_factory=list)
    schedules: list[ScheduleRow] = field(default_factory=list)


def _web_ui_url(options: TemporalOptions, *parts: str) -> str | None:
    """Build a Temporal Web UI URL for ``parts`` under the configured base."""
    if options.web_ui_url is None:
        return None
    segments = [options.web_ui_url, "namespaces", quote(options.namespace, safe="")]
    segments.extend(quote(part, safe="") for part in parts)
    return "/".join(segments)


def _cadence(config: ScheduleConfig) -> str:
    if config.cron is not None:
        return f"cron {config.cron}"
    return f"every {config.every}"


def _workflow_row(
    options: TemporalOptions, execution: temporalio.client.WorkflowExecution
) -> WorkflowRow:
    return WorkflowRow(
        id=execution.id,
        workflow_type=execution.workflow_type,
        status=execution.status.name if execution.status else "UNKNOWN",
        task_queue=execution.task_queue,
        start_time=execution.start_time,
        close_time=execution.close_time,
        url=_web_ui_url(options, "workflows", execution.id, execution.run_id),
    )


def _schedule_row(
    options: TemporalOptions,
    entry: temporalio.client.ScheduleListDescription,
    configs: dict[str, ScheduleConfig],
) -> ScheduleRow:
    config = configs.get(entry.id)
    listed = entry.schedule
    next_action_time = (
        entry.info.next_action_times[0]
        if entry.info is not None and entry.info.next_action_times
        else None
    )
    if listed is not None:
        paused: bool | None = listed.state.paused
    elif config is not None:
        paused = config.paused
    else:
        paused = None
    return ScheduleRow(
        id=entry.id,
        task=config.task_path if config is not None else None,
        cadence=_cadence(config) if config is not None else None,
        paused=paused,
        next_action_time=next_action_time,
        url=_web_ui_url(options, "schedules", entry.id),
    )


def _temporal_aliases() -> list[str]:
    """Return the task backend aliases that use the Temporal backend."""
    aliases: list[str] = []
    for alias in task_backends:
        try:
            backend = task_backends[alias]
        except Exception:
            logger.exception("Could not load the task backend %r.", alias)
            continue
        if isinstance(backend, TemporalTaskBackend):
            aliases.append(alias)
    return aliases


async def _overview_for(alias: str) -> AliasOverview:
    try:
        options = get_options(alias)
        configs = {config.id: config for config in parse_schedules(alias)}
    except ImproperlyConfigured as exc:
        return AliasOverview(
            alias=alias,
            namespace="",
            web_ui_url=None,
            error=str(exc) or type(exc).__name__,
        )

    try:
        temporal = await connect(options)
        workflows = [
            _workflow_row(options, execution)
            async for execution in temporal.list_workflows(limit=WORKFLOW_LIMIT)
        ]
        schedules: list[ScheduleRow] = []
        async for entry in await temporal.list_schedules(page_size=SCHEDULE_LIMIT):
            schedules.append(_schedule_row(options, entry, configs))
            if len(schedules) >= SCHEDULE_LIMIT:
                break
    except Exception as exc:  # the admin must render any failure
        logger.warning(
            "Could not read Temporal data for the task backend %r.",
            alias,
            exc_info=True,
        )
        return AliasOverview(
            alias=alias,
            namespace=options.namespace,
            web_ui_url=_web_ui_url(options, "workflows"),
            error=str(exc) or type(exc).__name__,
        )

    schedules.sort(key=lambda row: row.id)
    return AliasOverview(
        alias=alias,
        namespace=options.namespace,
        web_ui_url=_web_ui_url(options, "workflows"),
        workflows=workflows,
        schedules=schedules,
    )


async def _collect_overviews() -> list[AliasOverview]:
    return [await _overview_for(alias) for alias in _temporal_aliases()]


@admin.register(TemporalOverview)
class TemporalOverviewAdmin(admin.ModelAdmin):
    """Read-only page whose rows come from Temporal, not the database."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def changelist_view(
        self, request: HttpRequest, extra_context: dict[str, Any] | None = None
    ) -> HttpResponse:
        if not self.has_view_permission(request):
            raise PermissionDenied
        context: dict[str, Any] = {
            **self.admin_site.each_context(request),
            **(extra_context or {}),
            "title": "Temporal",
            "opts": self.model._meta,
            "overviews": async_to_sync(_collect_overviews)(),
        }
        return TemplateResponse(
            request, "admin/django_tasks_temporal/overview.html", context
        )
