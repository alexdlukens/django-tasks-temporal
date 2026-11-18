import os

SECRET_KEY = "django-tasks-temporal-tests"
DEBUG = True
USE_TZ = True
ROOT_URLCONF = "tests.urls"
STATIC_URL = "static/"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django_tasks_temporal",
    "tests.app",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
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
        "OPTIONS": {
            "ADDRESS": TEMPORAL_TEST_ADDRESS,
            "WEB_UI_URL": "http://localhost:8233",
        },
    },
    "scheduled": {
        "BACKEND": BACKEND,
        "QUEUES": ["default"],
        "OPTIONS": {
            "ADDRESS": TEMPORAL_TEST_ADDRESS,
            "WEB_UI_URL": "http://localhost:8233",
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
