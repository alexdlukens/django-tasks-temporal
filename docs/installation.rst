Installation
============

Requirements
------------

* Python 3.12 or later.
* Django 6.0 or later, for the ``django.tasks`` framework.
* ``temporalio`` 1.36 or later.
* A Temporal server: a local development server or a self-hosted deployment.

Install the package
-------------------

With `uv <https://docs.astral.sh/uv/>`__:

.. code-block:: console

   uv add django-tasks-temporal

With pip:

.. code-block:: console

   python -m pip install django-tasks-temporal

Add ``"django_tasks_temporal"`` to ``INSTALLED_APPS`` so Django finds the
package's management commands:

.. code-block:: python

   INSTALLED_APPS = [
       # ...
       "django_tasks_temporal",
   ]

Run a Temporal server
---------------------

Every enqueue and every worker connects to a Temporal server. For local
development, install the Temporal CLI (see the `Temporal CLI documentation
<https://docs.temporal.io/cli>`__) and start the development server:

.. code-block:: console

   temporal server start-dev

The development server listens for gRPC connections on ``localhost:7233`` and
serves its web UI at http://localhost:8233. These are the defaults used by the
backend; see :doc:`configuration` to point at another address or namespace.

Next steps
----------

Configure the backend in :doc:`configuration`, then see :doc:`activities` for
defining and enqueueing tasks.
