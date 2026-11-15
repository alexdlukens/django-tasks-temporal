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

## Release

Two entry points, both publishing a wheel and sdist on the GitHub release:

- **Actions → Bump version → Run workflow**, with the version in the `version`
  input (e.g. `0.2.0`). That workflow sets `pyproject.toml` and `uv.lock` to the
  version, commits to the default branch, creates the annotated tag `v0.2.0`,
  pushes both atomically, then runs the `Release` workflow for the tag.
- **Push a `v*` tag** yourself (`git tag -a v0.2.0 && git push origin v0.2.0`).
  `Release` derives the version from the tag (`v0.2.0` → `0.2.0`), builds, and
  creates or updates the release.

The version must be canonical PEP 440 (`0.2.0`, `0.3.0rc1`); inputs that would
normalize (`v0.2.0`, `0.3.0-rc`) are rejected, as is a tag that already exists
on `origin`. Tag pushes made with `GITHUB_TOKEN` do not trigger `push`
workflows, so `Bump version` calls `Release` directly via `workflow_call`.

## Documentation

Published at <https://alexdlukens.github.io/django-tasks-temporal/>. Sources
live in `docs/` and build with Sphinx; the `Docs` workflow deploys them to
GitHub Pages. Read the Docs configuration remains in `.readthedocs.yaml`.
