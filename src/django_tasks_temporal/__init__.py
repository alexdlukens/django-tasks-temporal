"""Django tasks backend that runs tasks on Temporal.

Configure the backend with ``BACKEND="django_tasks_temporal.backend.TemporalTaskBackend"``.
This package root intentionally imports nothing: the Temporal workflow sandbox
imports it, and it must stay free of Django imports.
"""
