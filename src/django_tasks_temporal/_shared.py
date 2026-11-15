"""Names and wire types shared by the backend, worker, and scheduler.

Changing anything here is a cross-module contract change: update the backend,
the workflow/activity module, and the scheduler together.
"""

from dataclasses import dataclass
from typing import Any

# Temporal workflow type name for the generic Django task workflow.
WORKFLOW_NAME = "django_tasks_temporal.DjangoTaskWorkflow"

# Temporal activity name for the generic Django task activity.
ACTIVITY_NAME = "django_tasks_temporal.run_task"

# Default Django backend alias used by the management commands.
DEFAULT_BACKEND_ALIAS = "default"


@dataclass(frozen=True, slots=True)
class TaskInput:
    """Single argument passed to DjangoTaskWorkflow and run_task.

    Temporal serializes this as JSON, so only JSON-compatible values belong in
    args/kwargs. Django's TaskResult already normalizes args/kwargs to JSON.
    """

    task_path: str  # Dotted import path to the module-level Task instance.
    args: list[Any]
    kwargs: dict[str, Any]


def temporal_priority_key(django_priority: int) -> int:
    """Map a Django task priority to a Temporal priority key.

    Django: higher number runs first, range [-100, 100], default 0.
    Temporal: lower key runs first, range 1..5 (server default max is 5), default 3.
    """
    return max(1, min(5, 3 - round(django_priority / 50)))
