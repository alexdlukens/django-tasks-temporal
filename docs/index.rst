django-tasks-temporal
=====================

A `Django tasks <https://docs.djangoproject.com/en/stable/topics/tasks/>`__
backend that runs Django task functions on `Temporal <https://temporal.io>`__.

``django-tasks-temporal`` plugs into Django's ``TASKS`` setting, so code that
already uses ``@task``, ``.enqueue()``, and ``.get_result()`` keeps working
unchanged. Every enqueue becomes one Temporal workflow execution that runs the
Django task function as a Temporal activity.

Features
--------

* A Django task backend, ``TemporalTaskBackend``, selected with the normal
  ``TASKS`` setting.
* Django task functions run as Temporal activities on the task queue named by
  the Django task's ``queue_name``.
* Temporal workflows, both the generic workflow used by the backend and your
  own workflows decorated with
  ``@django_tasks_temporal.workflows.workflow``.
* ``execute_task()`` to call a Django task as an activity from inside a custom
  workflow.
* Scheduled tasks: Temporal Schedules declared in the backend's ``SCHEDULES``
  option and synced from Django management commands.
* A ``run_temporal_worker`` management command that serves one Temporal worker
  per Django queue.
* A ``sync_temporal_schedules`` management command that creates or updates the
  declared schedules.
* Result retrieval, including task arguments, attempts, worker identities, and
  failure tracebacks reconstructed from Temporal workflow history.
* An optional read-only Django admin page listing recent workflow executions
  and schedules, with links to the Temporal Web UI.
* Priority, ``run_after`` deferral, and ``takes_context`` support through
  Django's task API.

.. note::

   A Temporal server is required. For local development, run
   ``temporal server start-dev``; it listens on ``localhost:7233``.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   installation
   configuration
   activities
   workflows
   schedules
   admin
   workers
   results
   architecture
   security
   development
   api

Indices and search
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
