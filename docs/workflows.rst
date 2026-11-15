Workflows
=========

Temporal workflows orchestrate activities and hold the durable state of an
execution. The backend itself uses one generic workflow per enqueue (see
:doc:`architecture`), but you can define your own workflows and call Django
tasks from them as activities.

Defining and registering a workflow
-----------------------------------

Use ``@django_tasks_temporal.workflows.workflow`` on the class and Temporal's own
``@temporalio.workflow.run`` on the entry point. The decorator wraps
``temporalio.workflow.defn`` and registers the class so the workers started by
``run_temporal_worker`` serve it:

.. code-block:: python

   # reports/tasks.py
   from temporalio import workflow as temporal_workflow

   from django_tasks_temporal.workflows import execute_task, workflow

   with temporal_workflow.unsafe.imports_passed_through():
       from django.tasks import task


   @task(backend="default")
   def send_daily_report(recipient: str) -> str:
       return f"sent the report to {recipient}"


   @workflow
   class SendReportsWorkflow:
       @temporal_workflow.run
       async def run(self, recipient: str) -> str:
           return await execute_task(send_daily_report, recipient)

Django imports in a workflow module must be wrapped in
``workflow.unsafe.imports_passed_through()`` as shown, because the module is
imported by the workflow sandbox. See :ref:`workflow-sandbox` below.

The decorator can also name the workflow type explicitly:

.. code-block:: python

   @workflow(name="reports.SendReportsWorkflow")
   class SendReportsWorkflow:
       ...

Workflow classes must be imported when the worker starts. The worker command
imports each installed app's ``tasks`` module, so define workflows in
``<app>/tasks.py`` or import them from that module.

Calling a Django task with ``execute_task``
-------------------------------------------

``execute_task(task, *args, **kwargs)`` schedules the Django task as the
``django_tasks_temporal.run_task`` activity and returns its return value:

.. code-block:: python

   @workflow
   class ImportWorkflow:
       @temporal_workflow.run
       async def run(self, path: str) -> None:
           await execute_task(import_users, path)
           await execute_task(send_daily_report, "ops@example.com")

Details:

* The activity runs on the task's own queue: ``task.queue_name`` becomes the
  activity's ``task_queue``, so a worker must be serving that queue.
* The task's ``priority`` is mapped to a Temporal activity priority exactly as
  it is for enqueued tasks (see :doc:`activities`).
* The activity uses the same 24-hour start-to-close timeout and
  ``maximum_attempts=1`` retry policy as the backend's generic workflow.
* An exception from the task fails the activity; inside the workflow it
  surfaces as a ``temporalio.exceptions.ActivityError`` whose cause is the
  ``ApplicationError`` carrying the exception class path and traceback. Catch
  it in workflow code if the workflow should continue.
* The task must be a module-level Django ``Task`` instance, because the
  activity resolves it from its dotted import path.

``execute_task`` is only valid inside workflow code. Calling it from an
activity or ordinary Django code raises Temporal's sandbox/runtime error.

.. _workflow-sandbox:

Workflow sandbox and Django imports
-----------------------------------

Workflow code runs in Temporal's deterministic sandbox. Importing Django
directly into sandboxed modules fails, so any Django import in a workflow
module must be passed through explicitly:

.. code-block:: python

   from temporalio import workflow

   with workflow.unsafe.imports_passed_through():
       from django.contrib.auth.models import User

Always import Django models and other Django modules through
``imports_passed_through()`` in workflow modules. The backend's own workflow
module already does this.

Workflow code must be deterministic: do database queries, HTTP calls, and other
side effects inside a Django task (which runs as an activity), never directly
in a workflow.

Starting a workflow from Django code
------------------------------------

There is no Django-facing API for starting custom workflows beyond the
``workflow`` decorator and ``execute_task``. Use the ``temporalio`` client
directly, configured with the same connection options as the backend:

.. code-block:: python

   from django_tasks_temporal.client import connect, get_options


   async def start_send_reports(recipient: str) -> str:
       client = await connect(get_options("default"))
       handle = await client.start_workflow(
           SendReportsWorkflow.run,
           recipient,
           id="send-reports-2026-11-15",
           task_queue="reports",
       )
       return handle.id

Or use ``temporalio.client.Client.connect()`` with explicit options. The
worker serving the workflow must have discovered the workflow class, and the
workflow's task queue must match one the worker serves. Workflow ids must be
unique among running executions; choose ids that fit your application's
idempotency requirements.

The enqueue API for ordinary Django tasks remains ``Task.enqueue()`` and
``Task.aenqueue()``; custom workflows are an advanced escape hatch for
orchestration that spans multiple tasks.
