Scheduled tasks
===============

Temporal Schedules run a Django task on a cron expression or at a fixed
interval. Schedules are declared in the backend's ``OPTIONS["SCHEDULES"]`` and
pushed to Temporal with a management command. Each schedule entry starts the
generic ``django_tasks_temporal.DjangoTaskWorkflow`` for the Django task, so the
task executes as an activity exactly as it does for an enqueue.

Declaring a schedule
--------------------

.. code-block:: python

   from datetime import timedelta

   TASKS = {
       "default": {
           "BACKEND": "django_tasks_temporal.backend.TemporalTaskBackend",
           "QUEUES": ["default", "reports"],
           "OPTIONS": {
               "SCHEDULES": [
                   {
                       "id": "send-daily-report",
                       "task": "reports.tasks.send_daily_report",
                       "cron": "0 6 * * *",
                       "kwargs": {"recipient": "ops@example.com"},
                   },
                   {
                       "id": "refresh-cache",
                       "task": "reports.tasks.refresh_cache",
                       "every": timedelta(minutes=15),
                       "args": ["summary"],
                       "paused": False,
                   },
               ],
           },
       },
   }

Schedule entry schema
---------------------

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
     - Unique Temporal Schedule id within the namespace. Non-empty.
   * - ``task``
     - yes
     - ``str``
     - Dotted import path to a module-level Django ``Task`` instance, for
       example ``"reports.tasks.send_daily_report"``.
   * - ``cron``
     - one of
     - ``str``
     - Standard five-field cron expression (minute, hour, day of month, month,
       day of week) evaluated in UTC. Mutually exclusive with ``every``.
   * - ``every``
     - one of
     - ``timedelta`` or ``int``
     - Fixed positive interval. An ``int`` is interpreted as seconds.
       Mutually exclusive with ``cron``.
   * - ``args``
     - no
     - ``list``
     - Positional arguments for the task. Defaults to ``[]``.
   * - ``kwargs``
     - no
     - ``dict``
     - Keyword arguments for the task. Defaults to ``{}``.
   * - ``paused``
     - no
     - ``bool``
     - Create the schedule paused. Defaults to ``False``.

Validation happens before any network call: missing or unknown keys, duplicate
ids, an entry with both or neither of ``cron``/``every``, non-positive
intervals, and tasks that are not module-level Django tasks using the selected
backend all raise ``django.core.exceptions.ImproperlyConfigured``.

The task's ``queue_name`` decides which Temporal task queue each run uses, so a
worker must be serving that queue.

Syncing schedules
-----------------

Schedules are applied by the ``sync_temporal_schedules`` management command:

.. code-block:: console

   python manage.py sync_temporal_schedules --backend default

The command validates every entry, connects with the backend's connection
options, then creates each Temporal Schedule. If a schedule with the same id
already exists, it is accepted only when it is a
``DjangoTaskWorkflow`` schedule carrying no marker or this backend alias's
marker; it is then updated in place with the new action, spec, and paused
state. A schedule owned by another alias, or any other workflow type, raises
``django.core.exceptions.ImproperlyConfigured`` instead of being overwritten.
It prints each synced schedule id, in configuration order.

Pruning removed schedules
-------------------------

By default syncing is create-or-update and never deletes anything. Pass
``--prune`` to also delete the Temporal Schedules this backend created for the
selected alias that are no longer declared:

.. code-block:: console

   python manage.py sync_temporal_schedules --backend default --prune

The command then prints each deleted id prefixed with ``pruned``.

Every schedule the command creates or updates carries an ownership marker in
its start-workflow action memo: the key ``django_tasks_temporal`` with the
backend alias as the value. Pruning lists the schedules in the namespace,
ignores any that do not start
``django_tasks_temporal.DjangoTaskWorkflow`` or whose marker does not name the
selected backend alias, and deletes the remaining ids that are not in the
current ``SCHEDULES``. Two backend aliases can therefore share a namespace
without pruning each other's schedules. With an empty ``SCHEDULES``, pruning
removes every schedule previously managed for that alias.

The marker names the alias, not the deployment. Deployments that share a
namespace and use the same alias are treated as one owner and can prune each
other's schedules; give each deployment a distinct alias or namespace. See
:doc:`security` for the full trust model.

Schedules created before this marker existed carry no marker and are never
pruned (a later sync that updates them does add the marker). They are
indistinguishable from schedules created outside this backend, so delete them
manually (for example with the Temporal CLI) or let the namespace be cleaned
up.

Other caveats:

* Entries are not renamed. Changing an entry's ``id`` creates a new schedule
  under the new id; the old schedule is pruned on the next ``--prune`` run.
* Schedules are only pushed when the command runs. Changing settings does not
  update Temporal by itself; run the command as part of deployment.

Deleting a schedule manually:

.. code-block:: console

   temporal schedule delete --schedule-id send-daily-report

(or use the Temporal UI at http://localhost:8233 when running the development
server).

Examples
--------

Daily at 06:00 UTC:

.. code-block:: python

   {
       "id": "send-daily-report",
       "task": "reports.tasks.send_daily_report",
       "cron": "0 6 * * *",
   }

Every fifteen minutes, passing arguments:

.. code-block:: python

   {
       "id": "refresh-cache",
       "task": "reports.tasks.refresh_cache",
       "every": 15 * 60,
       "args": ["summary"],
       "kwargs": {"force": True},
   }

The same interval as a ``timedelta``:

.. code-block:: python

   {
       "id": "refresh-cache",
       "task": "reports.tasks.refresh_cache",
       "every": timedelta(minutes=15),
   }
