API reference
=============

Public API
----------

Backend
~~~~~~~

.. autoclass:: django_tasks_temporal.backend.TemporalTaskBackend
   :members:
   :show-inheritance:

Workflow helpers and module
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. autofunction:: django_tasks_temporal.workflows.workflow

.. autofunction:: django_tasks_temporal.workflows.execute_task

.. autoclass:: django_tasks_temporal.workflows.DjangoTaskWorkflow
   :members:
   :show-inheritance:

.. autofunction:: django_tasks_temporal.workflows.run_task

.. autofunction:: django_tasks_temporal.workflows.registered_workflows

Schedules module
~~~~~~~~~~~~~~~~

.. automodule:: django_tasks_temporal.schedules
   :members: ScheduleConfig, parse_schedules, sync_schedules
   :show-inheritance:

Client module
~~~~~~~~~~~~~

.. automodule:: django_tasks_temporal.client
   :members: TemporalOptions, connect, get_options
   :show-inheritance:

Worker module
~~~~~~~~~~~~~

.. automodule:: django_tasks_temporal.worker
   :members: create_worker, run_workers, discover
   :show-inheritance:
