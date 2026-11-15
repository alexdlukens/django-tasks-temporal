import os

SECRET_KEY = "django-tasks-temporal-tests"
DEBUG = True
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "tests.app",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# conftest.py starts a Temporal dev server on this address' port.
TEMPORAL_TEST_ADDRESS = os.environ.get("TEMPORAL_TEST_ADDRESS", "localhost:7233")

BACKEND = "django_tasks_temporal.backend.TemporalTaskBackend"

TASKS = {
    "default": {
        "BACKEND": BACKEND,
        "QUEUES": ["default", "high"],
        "OPTIONS": {"ADDRESS": TEMPORAL_TEST_ADDRESS},
    },
    "scheduled": {
        "BACKEND": BACKEND,
        "QUEUES": ["default"],
        "OPTIONS": {
            "ADDRESS": TEMPORAL_TEST_ADDRESS,
            "SCHEDULES": [
                {
                    "id": "test-every-paused",
                    "task": "tests.app.tasks.scheduled_tick",
                    "every": 3600,
                    "paused": True,
                },
                {
                    "id": "test-cron",
                    "task": "tests.app.tasks.scheduled_tick",
                    "cron": "0 9 * * *",
                },
            ],
        },
    },
}
