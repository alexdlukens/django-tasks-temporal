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

``"django_tasks_temporal"`` in ``INSTALLED_APPS`` is required for the
management commands (``run_temporal_worker`` and
``sync_temporal_schedules``) and the optional Django admin page (see
:doc:`admin`); the backend itself is imported by dotted path.

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
   * - ``API_KEY``
     - ``str``
     - ``None``
     - Bearer token for Temporal Cloud or another hosted service. TLS is
       enabled automatically; combining ``API_KEY`` with ``TLS: False``
       raises ``ImproperlyConfigured``.
   * - ``TLS``
     - ``bool`` or ``dict``
     - ``False``
     - Connect with TLS. A boolean enables or disables TLS with the system
       trust store. A mapping enables TLS and configures certificates:
       ``server_root_ca_cert`` (path to the root CA bundle), ``client_cert``
       and ``client_private_key`` (paths to the mTLS certificate and key,
       which must be given together), and ``domain`` (SNI host and the name
       the server certificate is verified against). File paths are read when
       the client connects.
   * - ``ACTIVITY_TIMEOUT``
     - ``timedelta`` or ``float``
     - 24 hours
     - Start-to-close timeout of the activity that runs each enqueued or
       scheduled task, as a ``timedelta`` or a number of seconds. A task still
       running after this long is timed out and its workflow fails. Applies
       to tasks started by this backend, not to ``execute_task`` calls.
   * - ``WEB_UI_URL``
     - ``str``
     - ``None``
     - Base URL of the Temporal Web UI, for example
       ``"http://localhost:8233"``. When set, the optional Django admin page
       links workflow executions and schedules to that UI. See
       :doc:`admin`.
   * - ``SCHEDULES``
     - ``list``
     - ``[]``
     - Declarative Temporal Schedules; see :doc:`schedules` for the entry
       schema.

Unknown option keys raise ``django.core.exceptions.ImproperlyConfigured``
instead of being silently ignored. ``SCHEDULES`` is consumed by the scheduler,
``ACTIVITY_TIMEOUT`` by the enqueue path, and ``WEB_UI_URL`` by the Django
admin.

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

Hosted services
---------------

Temporal Cloud authenticates with an API key; TLS is enabled automatically:

.. code-block:: python

   import os

   TASKS = {
       "default": {
           "BACKEND": "django_tasks_temporal.backend.TemporalTaskBackend",
           "OPTIONS": {
               "ADDRESS": "my-namespace.tmprl.cloud:7233",
               "NAMESPACE": "my-namespace",
               "API_KEY": os.environ["TEMPORAL_API_KEY"],
           },
       },
   }

Deployments that authenticate clients with certificates configure the
``TLS`` mapping with file paths:

.. code-block:: python

   OPTIONS = {
       "ADDRESS": "temporal.example.com:7233",
       "NAMESPACE": "default",
       "TLS": {
           "server_root_ca_cert": "/etc/temporal/ca.pem",
           "client_cert": "/etc/temporal/client.pem",
           "client_private_key": "/etc/temporal/client-key.pem",
           "domain": "temporal.example.com",
       },
   }

Certificate files are read when a client is created, which happens once per
event loop and option set. Rotate the files and restart the worker or process
to pick them up.

Connection options apply to the management commands and to enqueues made by the
backend. Enqueuing a task requires a reachable Temporal server.

Next steps
----------

* :doc:`activities` — define and enqueue Django tasks.
* :doc:`workers` — run the workers that execute tasks.
* :doc:`schedules` — sync cron and interval schedules.
