Development
===========

From a checkout of this repository:

.. code-block:: console

   uv sync

``uv sync`` installs the project in editable mode along with the ``dev``
dependency group (pytest, pytest-django, ruff, mypy). Sphinx and furo live in
the separate ``docs`` group.

Tests
-----

.. code-block:: console

   uv run pytest

The project uses pytest-django with ``DJANGO_SETTINGS_MODULE=tests.settings``
and ``pythonpath = ["."]``, configured in ``pyproject.toml``.

Linting and type checking
-------------------------

.. code-block:: console

   uv run ruff check .
   uv run mypy

``mypy`` runs in strict mode over ``src``.

Building the docs
-----------------

.. code-block:: console

   uv run --group docs sphinx-build -b html docs docs/_build/html

The HTML output is written to ``docs/_build/html``. The Read the Docs build
uses ``.readthedocs.yaml`` and the same Sphinx sources.

Local Temporal server
---------------------

Running an integration check against a real server requires the Temporal CLI:

.. code-block:: console

   temporal server start-dev

The development server listens on ``localhost:7233`` (the backend's default
``ADDRESS``) in the ``default`` namespace (the default ``NAMESPACE``). Its web
UI is at http://localhost:8233, where you can inspect workflow executions,
activities, and schedules created by the worker and scheduler.
