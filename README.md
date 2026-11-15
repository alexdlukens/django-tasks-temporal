# django-tasks-temporal

A [Django tasks](https://docs.djangoproject.com/en/stable/topics/tasks/) backend
that runs Django task functions on [Temporal](https://temporal.io). Each
enqueue becomes one Temporal workflow execution that runs the function as an
activity, with result retrieval, workers, and scheduled tasks.

## Install

```console
uv add django-tasks-temporal
```

Requires Python 3.12+, Django 6.0+, temporalio 1.36+, and a Temporal server
(`temporal server start-dev` for local development).

## Configure

```python
INSTALLED_APPS = [
    # ...
    "django_tasks_temporal",
]

TASKS = {
    "default": {
        "BACKEND": "django_tasks_temporal.backend.TemporalTaskBackend",
        "QUEUES": ["default"],
        "OPTIONS": {"ADDRESS": "localhost:7233", "NAMESPACE": "default"},
    },
}
```

## Define and run a task

```python
# reports/tasks.py
from django.tasks import task


@task(backend="default")
def send_report(recipient: str) -> str:
    return f"sent to {recipient}"
```

```console
python manage.py run_temporal_worker --backend default
```

```python
from reports.tasks import send_report

result = send_report.enqueue("ops@example.com")
finished = send_report.get_result(result.id)
print(finished.return_value)
```

Documentation sources live in `docs/` and build with Sphinx; Read the Docs
configuration is `.readthedocs.yaml`.
