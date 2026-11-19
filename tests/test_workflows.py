"""Unit tests for workflow-side input hardening."""

from datetime import timedelta

import pytest

from django_tasks_temporal.workflows import (
    DEFAULT_ACTIVITY_TIMEOUT,
    _activity_timeout,
)


def test_activity_timeout_accepts_positive_seconds():
    assert _activity_timeout(90) == timedelta(seconds=90)


@pytest.mark.parametrize(
    "value", [0, -1, "invalid", None, float("nan"), float("inf"), 1e300]
)
def test_activity_timeout_falls_back_for_forged_values(value):
    assert _activity_timeout(value) == DEFAULT_ACTIVITY_TIMEOUT
