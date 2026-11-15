Workers
=======

Temporal workers poll task queues and execute the workflows and activities
they are configured to serve. ``django-tasks-temporal`` provides a management
command that starts them with Django configured.

Running workers
---------------

.. code-block:: console

   python manage.py run_temporal_worker --backend default

This starts one Temporal worker per queue in the backend's ``QUEUES`` setting
(``["default", "reports"]`` in the :doc:`configuration` example). To serve a
subset, repeat ``--queue``:

.. code-block:: console

   python manage.py run_temporal_worker --backend default --queue default
   python manage.py run_temporal_worker --backend default --queue reports

Each worker serves:

* the generic ``django_tasks_temporal.DjangoTaskWorkflow`` workflow,
* every workflow class registered with
  ``@django_tasks_temporal.workflows.workflow``,
* the ``django_tasks_temporal.run_task`` activity.

Options
-------

``--backend``
   Alias in ``TASKS`` to serve. Defaults to ``default``.

``--queue``
   Temporal task queue to serve; may be repeated. Defaults to every queue in
   the backend's ``QUEUES``. If ``QUEUES`` is empty, the command raises
   ``ImproperlyConfigured`` unless at least one ``--queue`` is given, because
   there is no queue to derive from the settings.

Task discovery
--------------

Before connecting, the command calls Django's
``autodiscover_modules("tasks")`` for every installed app. Importing
``<app>/tasks.py`` modules registers:

* the Django tasks defined there, and
* workflow classes decorated with
  ``@django_tasks_temporal.workflows.workflow`` that are imported by those
  modules.

Because of this, a custom workflow must be defined in or imported from an
app's ``tasks.py``; otherwise the worker will not know it and Temporal will not
be able to dispatch its workflow tasks. See :doc:`workflows`.

Shutdown
--------

``Ctrl-C`` shuts the workers down gracefully: the command cancels them, waits
for in-flight activities to finish, then exits. The same shutdown path runs if
one worker fails fatally; the failure is re-raised after cleanup.

Multiple processes
------------------

Running several worker processes (or containers) is supported. They can all
poll the same task queues; Temporal distributes workflow and activity tasks
among them. Each process only serves the queues it was given, and activities
for a task run on the task's ``queue_name``.

What workers do not do
----------------------

The worker command does not sync schedules and does not enqueue tasks. Run
``sync_temporal_schedules`` separately (see :doc:`schedules`), typically during
deployment, and enqueue tasks from Django code as described in
:doc:`activities`.
