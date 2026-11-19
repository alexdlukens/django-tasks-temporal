"""Integration tests for the optional Django admin overview."""

from __future__ import annotations

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.tasks import TaskResultStatus, task_backends
from django.test import Client
from django.urls import reverse

from django_tasks_temporal.schedules import sync_schedules
from tests.app.tasks import add
from tests.test_backend import wait_for

OVERVIEW_URL = "admin:django_tasks_temporal_temporaloverview_changelist"
WEB_UI_URL = "http://localhost:8233"


def _admin_client() -> Client:
    user = get_user_model().objects.create_superuser(
        "admin", "admin@example.com", "password"
    )
    client = Client()
    client.force_login(user)
    return client


def test_overview_lists_recent_workflows_with_web_ui_links(db):
    result = add.enqueue(2, 3)
    wait_for(result, TaskResultStatus.SUCCESSFUL)

    response = _admin_client().get(reverse(OVERVIEW_URL))

    assert response.status_code == 200
    content = response.content.decode()
    assert result.id in content
    assert (
        f"{WEB_UI_URL}/namespaces/default/workflows/{result.id}/" in content
    )


def test_overview_hides_configuration_details(db, monkeypatch):
    monkeypatch.setitem(task_backends["default"].options, "API_KEY", b"super-secret")

    response = _admin_client().get(reverse(OVERVIEW_URL))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Temporal options are invalid" in content
    assert "super-secret" not in content


def test_overview_lists_schedules_with_web_ui_links(db):
    assert async_to_sync(sync_schedules)("scheduled") == [
        "test-every-paused",
        "test-cron",
    ]

    response = _admin_client().get(reverse(OVERVIEW_URL))

    assert response.status_code == 200
    content = response.content.decode()
    assert "test-cron" in content
    assert "tests.app.tasks.scheduled_tick" in content
    assert f"{WEB_UI_URL}/namespaces/default/schedules/test-cron" in content
