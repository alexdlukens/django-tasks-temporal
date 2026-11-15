Results
=======

Results are read from Temporal workflow executions. Each Django task result id
is a Temporal workflow id, so ``get_result()`` / ``aget_result()`` look up the
workflow by id and rebuild a :class:`django.tasks.TaskResult`.

Status mapping
--------------

.. list-table::
   :header-rows: 1
   :widths: 55 45

   * - Temporal workflow status
     - Django ``TaskResultStatus``
   * - ``RUNNING`` with no activity attempt yet
     - ``READY``
   * - ``COMPLETED``
     - ``SUCCESSFUL``
   * - ``FAILED``, ``CANCELED``, ``TERMINATED``, ``TIMED_OUT``
     - ``FAILED``
   * - ``CONTINUED_AS_NEW`` and any unknown status
     - ``RUNNING``

``READY`` means the workflow execution exists but its activity has not started
on a worker yet. ``RUNNING`` means the activity has been attempted and the
workflow has not finished.

Reading a result
----------------

.. code-block:: python

   result = send_report.enqueue("ops@example.com")

   current = send_report.get_result(result.id)
   if current.is_finished:
       print(current.status)
       print(current.return_value)

   # Async:
   current = await send_report.aget_result(result.id)

``get_result()`` does not wait for completion; it reports the current state.
Poll (or call ``result.refresh()`` / ``await result.arefresh()`` on an existing
``TaskResult``) if you need to observe a task until it finishes.

Fields
------

The backend reconstructs these fields from the workflow execution:

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Field
     - Source
   * - ``id``
     - The Temporal workflow id.
   * - ``task``
     - Imported from ``task_path`` in the workflow's ``TaskInput`` argument.
   * - ``status``
     - Mapped from the workflow status as shown above.
   * - ``args`` / ``kwargs``
     - Decoded from the workflow's start input (``TaskInput``).
   * - ``enqueued_at``
     - Workflow start time.
   * - ``started_at``
     - First activity attempt start time, or the pending attempt's start time
       while it has not produced a history event yet.
   * - ``last_attempted_at``
     - Most recent activity attempt start time.
   * - ``finished_at``
     - Workflow close time, or ``None`` while it is still open.
   * - ``worker_ids``
     - Temporal activity worker identities, one per attempt. When an identity
       is not recorded, ``attempt-<n>`` is used. ``TaskResult.attempts`` is the
       length of this list.
   * - ``errors``
     - For failed results, one ``TaskError`` with the failing exception's
       class path and traceback.
   * - ``return_value``
     - For successful results, the task function's return value.

Errors
------

When a task raises, the activity re-raises it as a Temporal
``ApplicationError`` whose error type is the exception's dotted class path
(``module.qualname``) and whose first string detail is the formatted traceback.
Reading the result walks the failure chain to the deepest ``ApplicationError``
and creates:

.. code-block:: python

   TaskError(
       exception_class_path="reports.exceptions.ReportFailed",
       traceback="Traceback (most recent call last): ...",
   )

If the failure did not originate from a Django task exception (for example, the
workflow was terminated or the worker died), the deepest available exception's
class and traceback are used instead.

Missing results
---------------

``get_result()`` raises
:class:`django.tasks.exceptions.TaskResultDoesNotExist` when no workflow
execution with that id exists in the configured namespace. Django additionally
raises ``TaskResultMismatch`` when a result exists but belongs to a different
task; call ``get_result()`` on the task that produced the id.

Network and history cost
------------------------

A result read performs a workflow describe, a full history fetch (for the
workflow input and activity attempts), and for finished executions a result
fetch. Results are not stored in a Django database, so there is no local task
table to prune; Temporal's namespace retention controls how long results remain
readable.
