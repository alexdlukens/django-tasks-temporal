Configuration
=============

The backend is selected through Django's ``TASKS`` setting. The alias is
arbitrary; the examples use ``default``.

.. code-block:: python

   from datetime import timedelta

   INSTALLED_APPS = [
       # ...
       "django_tasks_temporal",
   ]

   TASKS = {
       "default": {
           "BACKEND": "django_tasks_temporal.backend.TemporalTaskBackend",
           "QUEUES": ["default", "reports"],
           "OPTIONS": {
               "ADDRESS": "localhost:7233",
               "NAMESPACE": "default",
               "TLS": False,
               "SCHEDULES": [
                   {
                       "id": "send-daily-report",
                       "task": "reports.tasks.send_daily_report",
                       "cron": "0 6 * * *",
                   },
                   {
                       "id": "refresh-cache",
                       "task": "reports.tasks.refresh_cache",
                       "every": timedelta(minutes=15),
                       "args": ["summary"],
                       "kwargs": {"force": True},
                       "paused": False,
                   },
               ],
           },
       },
   }

``"django_tasks_temporal"`` in ``INSTALLED_APPS`` is required only for the
management commands (``run_temporal_worker`` and
``sync_temporal_schedules``); the backend itself is imported by dotted path.

``QUEUES``
----------

``QUEUES`` is Django's list of task queues served by this backend. Every queue
becomes a Temporal task queue of the same name. Tasks use the ``default`` queue
unless they set ``queue_name`` with ``@task(...)`` or
``.using(queue_name=...)``; Django validates that the queue is listed.

The worker command serves every configured queue unless ``--queue`` is passed
(see :doc:`workers`).

``OPTIONS``
-----------

.. list-table::
   :header-rows: 1
   :widths: 15 12 18 55

   * - Key
     - Type
     - Default
     - Description
   * - ``ADDRESS``
     - ``str``
     - ``"localhost:7233"``
     - gRPC address of the Temporal frontend, as ``host:port``.
   * - ``NAMESPACE``
     - ``str``
     - ``"default"``
     - Temporal namespace where workflow executions and schedules are created.
   * - ``TLS``
     - ``bool``
     - ``False``
     - Connect with TLS. Only the TLS switch is configurable; API keys and
       client certificates for hosted services are not supported.
   * - ``SCHEDULES``
     - ``list``
     - ``[]``
     - Declarative Temporal Schedules; see :doc:`schedules` for the entry
       schema.

Unknown option keys raise ``django.core.exceptions.ImproperlyConfigured``
instead of being silently ignored. ``SCHEDULES`` is accepted here and consumed
by the scheduler.

Each ``SCHEDULES`` entry accepts these keys:

.. list-table::
   :header-rows: 1
   :widths: 12 12 22 54

   * - Key
     - Required
     - Type
     - Description
   * - ``id``
     - yes
     - ``str``
     - Unique Temporal Schedule id within the namespace.
   * - ``task``
     - yes
     - ``str``
     - Dotted path to a module-level Django ``Task`` using this backend.
   * - ``cron``
     - one of
     - ``str``
     - Five-field cron expression in UTC. Mutually exclusive with ``every``.
   * - ``every``
     - one of
     - ``timedelta`` or ``int``
     - Fixed interval; an integer is seconds. Mutually exclusive with ``cron``.
   * - ``args``
     - no
     - ``list``
     - Positional task arguments. Defaults to ``[]``.
   * - ``kwargs``
     - no
     - ``dict``
     - Keyword task arguments. Defaults to ``{}``.
   * - ``paused``
     - no
     - ``bool``
     - Create the schedule paused. Defaults to ``False``.

See :doc:`schedules` for validation rules, syncing, and examples.

Connection options apply to the management commands and to enqueues made by the
backend. Enqueuing a task requires a reachable Temporal server.

Next steps
----------

* :doc:`activities` — define and enqueue Django tasks.
* :doc:`workers` — run the workers that execute tasks.
* :doc:`schedules` — sync cron and interval schedules.
