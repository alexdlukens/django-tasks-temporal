Security
========

This page describes the trust boundaries of ``django-tasks-temporal`` and the
hardening in the library. Configuration (``TASKS`` options, ``INSTALLED_APPS``,
task import paths, schedules) is written by the operator and is trusted.

Temporal namespace access
-------------------------

A Temporal namespace is the security boundary, not an individual workflow
type. ``DjangoTaskWorkflow`` is a public, data-driven workflow: its payload
names a Django task and carries its arguments. Anyone who can start workflows
on a task queue served by a worker can therefore invoke the application's
Django tasks with chosen arguments.

The worker validates each payload before running it:

* ``task_path`` must resolve to a Django ``Task`` instance, not an arbitrary
  object;
* the task's ``queue_name`` must match the queue delivering the activity;
* ``args`` must be a list, ``kwargs`` a dict, and a forged or invalid activity
  timeout falls back to the default instead of poisoning the workflow.

These checks prevent malformed payloads and accidental method dispatch. They
cannot authenticate the sender. Run workers in a namespace that only trusted
principals can write to, and use separate namespaces for separate trust
domains. Do not give untrusted applications or tenants an API key or client
that can start workflows in a worker's namespace.

Anyone who can read the namespace can read task arguments, results, and
failure details. Failed tasks store their exception message and full traceback
in Temporal history and failure details, where the namespace retention policy
keeps them. Treat the namespace as sensitive as your application database.

Result ids
----------

``TaskResult.id`` is a random ``uuid4().hex`` workflow id, but it is an
identifier, not an authorization token. ``get_result()`` accepts any id in the
backend's namespace and returns data for it. It rejects executions whose
workflow type is not ``DjangoTaskWorkflow``, but any caller that can reach the
backend API and knows a result id can read that result. Do not expose raw
result ids or ``get_result()`` to untrusted callers without your own
authorization check.

Django admin
------------

The optional Temporal admin page is read-only. It requires the *Can view
Temporal* permission (or superuser status), which covers every Temporal
backend alias and namespace configured in the project. Configuration and
connection errors are written to the server log; the page only shows a generic
message so filesystem paths, internal endpoints, and credentials never reach
staff browsers.

``WEB_UI_URL`` is trusted operator configuration. It must be an ``http`` or
``https`` URL; workflow and schedule ids are percent-encoded before being
appended. Deep links do not authenticate against Temporal: the Web UI applies
its own access control.

Connection credentials
----------------------

``API_KEY`` is never included in ``TemporalOptions`` representations or
validation error messages, and ``ADDRESS`` must be a ``host:port`` value
without a URL scheme. The Temporal SDK silently drops boolean TLS settings for
scheme-prefixed addresses, so allowing a scheme could send a bearer token over
cleartext even though TLS was requested.

Schedules
---------

Temporal Schedule ids are namespace-global. Syncing refuses to overwrite a
schedule that carries another alias's ownership marker or that is not a
``DjangoTaskWorkflow`` schedule. Pruning only deletes schedules whose marker
names the selected backend alias. The marker is the alias name, not a
deployment identity: two deployments that share a namespace *and* use the
same alias are treated as the same owner. Give each deployment a distinct
alias (or namespace) if they share a Temporal server. Run at most one
``sync_temporal_schedules --prune`` per alias at a time, and review the
command's output before relying on pruning in production.
