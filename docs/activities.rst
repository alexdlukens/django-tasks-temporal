Activities
==========

Each Django task enqueued on the Temporal backend runs as a Temporal activity.
The activity executes the task function once per attempt; the enclosing
workflow execution represents that single enqueue.

Defining a task
---------------

Tasks must be module-level functions decorated with Django's ``@task``, in a
``tasks.py`` module inside an installed app:

.. code-block:: python

   # reports/tasks.py
   from django.tasks import task


   @task(backend="default")
   def send_daily_report(recipient: str, *, dry_run: bool = False) -> str:
       if dry_run:
           return f"would send the report to {recipient}"
       return f"sent the report to {recipient}"

The ``backend`` argument is the ``TASKS`` alias, which must match the key used
in :doc:`configuration` (``default`` throughout these docs). For example, if
the alias is named ``temporal``, the decorator is
``@task(backend="temporal")``.

Arguments are transported to Temporal as JSON, so task arguments and keyword
arguments must be JSON-serializable. Both synchronous and asynchronous task
functions are supported.

Enqueueing and results
----------------------

.. code-block:: python

   from reports.tasks import send_daily_report

   result = send_daily_report.enqueue("ops@example.com")
   print(result.id)

   # In async code:
   result = await send_daily_report.aenqueue("ops@example.com")

The returned :class:`~django.tasks.TaskResult` carries the id of the Temporal
workflow execution, which is also the id accepted by ``get_result()``. It is
``READY`` with no worker ids until a worker picks up the activity:

.. code-block:: python

   finished = send_daily_report.get_result(result.id)
   print(finished.status)
   print(finished.return_value)

   # In async code:
   finished = await send_daily_report.aget_result(result.id)

``get_result()`` reports the result's current state and does not block until
the task finishes. See :doc:`results` for status mapping and the fields that
are reconstructed from Temporal.

Task options
------------

Django's ``Task.using()`` returns a new task with different defaults. All three
options are supported:

.. code-block:: python

   from datetime import datetime, timedelta, timezone

   urgent = send_daily_report.using(
       queue_name="reports",
       priority=50,
       run_after=datetime.now(timezone.utc) + timedelta(minutes=10),
   )
   result = urgent.enqueue("ops@example.com")

``queue_name`` selects the Temporal task queue. It must be one of the backend's
``QUEUES``. ``priority`` and ``run_after`` are described below.

Priority
~~~~~~~~

Django priorities are ``-100`` to ``100``, where a higher number runs first;
the default is ``0``. Temporal priority keys are ``1`` to ``5``, where a lower
key runs first; the default is ``3``. The backend maps the two conventions as
follows:

.. code-block:: text

   key = max(1, min(5, 3 - round(priority / 50)))

.. list-table::
   :header-rows: 1
   :widths: 25 25

   * - Django priority
     - Temporal priority key
   * - ``100``
     - ``1``
   * - ``50``
     - ``2``
   * - ``0`` (default)
     - ``3``
   * - ``-50``
     - ``4``
   * - ``-100``
     - ``5``

The backend applies the mapped priority to the workflow start, and
``execute_task`` applies it to the activity it schedules. Temporal servers must
support priority for it to have any effect; see :doc:`architecture`.

Deferral with ``run_after``
~~~~~~~~~~~~~~~~~~~~~~~~~~~

``run_after`` is an aware :class:`datetime.datetime` (Django rejects naive
values when ``USE_TZ`` is enabled). The backend converts it to a Temporal start
delay for the workflow, so the task is not dispatched before that time.

Takes context
~~~~~~~~~~~~~

Set ``takes_context=True`` to receive a :class:`django.tasks.TaskContext` as
the first argument:

.. code-block:: python

   from django.tasks import task


   @task(backend="default", takes_context=True)
   def send_daily_report(context, recipient: str) -> str:
       attempt = context.attempt
       if attempt > 1:
           log_retry(recipient, attempt)
       return f"sent the report to {recipient}"

The context wraps a ``TaskResult`` whose id is the Temporal workflow id and
whose ``attempt`` property comes from Temporal's activity attempt counter.
Because automatic retries are disabled (below), the attempt is normally ``1``;
it increases only if the activity attempt is retried manually from the
Temporal UI or CLI. The synthesized context's ``worker_ids`` contains one
``attempt-<n>`` entry per attempt, so ``TaskContext.attempt`` stays consistent
with Django's semantics.

Retries and timeouts
--------------------

Enqueued tasks are attempted once. The workflow runs the activity with
``RetryPolicy(maximum_attempts=1)``, because Django tasks define no retry
policy and Temporal's default would retry a failed activity until the workflow
times out.

Each activity has a start-to-close timeout of 24 hours
(``DEFAULT_ACTIVITY_TIMEOUT``). A task still running after that is timed out
and the workflow fails. Exceptions raised by the task fail the workflow, and
the exception class path and traceback are available on the task result; see
:doc:`results`.

To retry, implement the retry loop inside the Django task or call it from a
custom workflow that supplies its own retry policy (see :doc:`workflows`).
