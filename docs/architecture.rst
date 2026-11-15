Architecture
============

``django-tasks-temporal`` is a thin adapter between Django's task API and
Temporal. It stores no task state of its own: Temporal owns queueing, retries,
schedules, and result history.

Execution model
---------------

One call to ``Task.enqueue()`` creates one Temporal workflow execution:

* The workflow id is the ``TaskResult.id`` and is generated with
  ``uuid4().hex``.
* The workflow type is ``django_tasks_temporal.DjangoTaskWorkflow``.
* The workflow runs on the Temporal task queue named by the Django task's
  ``queue_name``, which is one of the backend's ``QUEUES``.
* The workflow has a single activity, ``django_tasks_temporal.run_task``, on
  that same task queue.
* The activity imports the task's function by its dotted path, calls it, and
  returns its result.

Workflow input wire format
--------------------------

Both the workflow and the activity receive one ``TaskInput`` value. Temporal's
default data converter serializes it as JSON:

.. code-block:: json

   {
     "task_path": "reports.tasks.send_daily_report",
     "args": ["ops@example.com"],
     "kwargs": {"dry_run": false}
   }

``task_path`` is ``Task.module_path`` (``func.__module__`` plus
``func.__qualname__``), so tasks must be defined at module level with a stable
import path. ``args`` and ``kwargs`` must be JSON-compatible: Temporal's
default data converter serializes the whole ``TaskInput`` as JSON.

Run flow
--------

1. Django calls ``TemporalTaskBackend.enqueue(task, args, kwargs)``.
2. The backend generates the result id, connects using the configured
   ``ADDRESS``/``NAMESPACE``/``TLS`` options, and starts
   ``DjangoTaskWorkflow`` with a ``TaskInput``. ``run_after`` becomes the
   workflow's start delay, and the mapped task priority is applied to the
   workflow start.
3. A worker polling ``task.queue_name`` runs the workflow, which schedules
   ``run_task`` as an activity with a 24-hour start-to-close timeout and
   ``RetryPolicy(maximum_attempts=1)``.
4. ``run_task`` resolves the task, builds a ``TaskContext`` when the task takes
   context, calls the function, and returns the value or re-raises the
   exception as an ``ApplicationError``.
5. The workflow returns the activity value or fails with the activity failure.

The activity name and workflow name are part of the wire contract with the
Temporal server. They are defined once in ``_shared.py`` as ``ACTIVITY_NAME``
and ``WORKFLOW_NAME`` and must not change while executions are in flight.

Reading results
---------------

``get_result()`` describes the workflow execution, fetches its full history to
decode the ``TaskInput`` and activity attempts, then fetches the workflow result
when the execution has closed. It needs a reachable server and a namespace that
still retains the execution.

Why retries are disabled
------------------------

Temporal retries failed activities indefinitely by default. Django tasks have
no retry policy: ``enqueue()`` means "run this once", and failures are reported
through the task result. Enabling Temporal's default would make a failing task
run forever, which would surprise callers and consume worker capacity.
Consequently both the generic workflow and ``execute_task`` set
``maximum_attempts=1``.

Applications that want retries can implement a loop inside the Django task, or
orchestrate it in a custom workflow with an explicit retry policy (see
:doc:`workflows`).

Schedules
---------

``SCHEDULES`` entries are converted to Temporal Schedules whose action starts
``DjangoTaskWorkflow`` with the declared ``TaskInput``. The schedule's task
queue comes from the Django task's ``queue_name`` and its priority from the
task's priority. ``sync_temporal_schedules`` creates missing schedules and
updates existing ids; it never deletes schedules. See :doc:`schedules`.

Modules
-------

``django_tasks_temporal.backend``
   ``TemporalTaskBackend``: enqueue and result retrieval.

``django_tasks_temporal.workflows``
   ``DjangoTaskWorkflow``, the ``run_task`` activity, the ``workflow``
   registration decorator, and ``execute_task``.

``django_tasks_temporal.results``
   Rebuilds ``TaskResult`` objects from workflow executions.

``django_tasks_temporal.schedules``
   Validates ``SCHEDULES`` and creates or updates Temporal Schedules.

``django_tasks_temporal.worker``
   Discovers ``tasks`` modules, builds one worker per queue, and runs them.

``django_tasks_temporal.client``
   Connection options and per-event-loop client reuse.

``django_tasks_temporal._shared``
   Workflow/activity names and the ``TaskInput`` wire type shared by the
   modules above.

Limitations
-----------

* **No pruning.** Django does not track workflows, so nothing deletes old
  executions; Temporal namespace retention does. Removed ``SCHEDULES`` entries
  are likewise not deleted from Temporal.
* **Priority depends on the server.** Temporal servers must support priority
  for the mapped priority key to have any effect.
* **Result reads cost a round trip.** ``get_result()`` hits the server and, for
  arguments and attempts, fetches history. There is no local index.
* **One workflow per task.** Every enqueue creates a workflow execution plus an
  activity, which is more overhead than an activity-only design but gives
  durable orchestration and result history.
* **JSON arguments only.** Args and kwargs must survive JSON serialization.
* **No Django-facing workflow start API.** Custom workflows are started with
  the ``temporalio`` client directly.
* **Fixed activity timeout.** Tasks that legitimately run longer than 24 hours
  time out; the timeout is not configurable through Django task settings.
* **Code changes must be compatible with in-flight work.** Workers replay open
  workflows, so workflow code and task import paths must remain stable while
  executions are running.
