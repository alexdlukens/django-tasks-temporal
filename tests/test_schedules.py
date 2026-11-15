from datetime import timedelta

from asgiref.sync import async_to_sync
from django.conf import settings
from temporalio.client import Client, ScheduleRange

from django_tasks_temporal.schedules import sync_schedules

EXPECTED_IDS = ["test-every-paused", "test-cron"]


def describe_schedule(schedule_id: str):
    async def run():
        client = await Client.connect(settings.TEMPORAL_TEST_ADDRESS)
        return await client.get_schedule_handle(schedule_id).describe()

    return async_to_sync(run)()


def test_sync_creates_schedules_and_is_idempotent():
    assert async_to_sync(sync_schedules)("scheduled") == EXPECTED_IDS

    paused = describe_schedule("test-every-paused")
    assert paused.schedule.state.paused is True
    assert paused.schedule.spec.intervals[0].every == timedelta(hours=1)

    # A second sync hits the already-exists path and must update in place.
    assert async_to_sync(sync_schedules)("scheduled") == EXPECTED_IDS

    cron = describe_schedule("test-cron")
    # The server normalizes cron strings into calendar specs on describe.
    (calendar,) = cron.schedule.spec.calendars
    assert calendar.hour == (ScheduleRange(start=9, end=9, step=1),)
    assert calendar.minute == (ScheduleRange(start=0, end=0, step=1),)
    assert cron.schedule.state.paused is False
