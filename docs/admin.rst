Django admin
============

When ``django.contrib.admin`` is installed and ``django_tasks_temporal`` is in
``INSTALLED_APPS``, Django's admin autodiscovery registers a read-only
**Temporal** page at
``/admin/django_tasks_temporal/temporaloverview/``. It lists, for every task
backend alias that uses the Temporal backend:

* recent workflow executions: id, type, status, task queue, start and close
  times, newest first (up to 50);
* Temporal Schedules: id, the configured Django task and cadence, paused
  state, and next action time (up to 50).

The integration is optional: without ``django.contrib.admin`` the page is
never registered.

Temporal Web UI links
---------------------

Set ``WEB_UI_URL`` in the backend's ``OPTIONS`` to link the page to the
Temporal Web UI:

.. code-block:: python

   TASKS = {
       "default": {
           "BACKEND": "django_tasks_temporal.backend.TemporalTaskBackend",
           "QUEUES": ["default"],
           "OPTIONS": {
               "ADDRESS": "localhost:7233",
               "WEB_UI_URL": "http://localhost:8233",
           },
       },
   }

The alias header then links to the namespace's workflow list, each workflow
row links to its execution, and each schedule row links to its schedule.
``WEB_UI_URL`` must be an ``http://`` or ``https://`` URL; a trailing slash is
ignored. Without it the page still lists data, but renders no links.

Permissions
-----------

The page is backed by an unmanaged, table-less model, so it behaves like any
other admin model: users need the *Can view Temporal* permission (or
superuser status). That permission covers every Temporal backend alias and
namespace configured in the project. It is read-only; adding, changing, and
deleting are disabled.

If the Temporal server cannot be reached, or an alias has invalid options, the
page shows a generic error for that alias instead of failing the admin
request. The exception, including paths and connection details, is written to
the server log. See :doc:`security`.
