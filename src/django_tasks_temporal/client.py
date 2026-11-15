"""Temporal connection options and client construction.

Options live in ``TASKS[alias]["OPTIONS"]``. Only connection-related keys are
read here; ``SCHEDULES`` is consumed by :mod:`django_tasks_temporal.schedules`
and is ignored by the parser.
"""

import asyncio
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import temporalio.client
from django.core.exceptions import ImproperlyConfigured
from django.tasks import task_backends

DEFAULT_ADDRESS = "localhost:7233"
DEFAULT_NAMESPACE = "default"
DEFAULT_TLS = False

_CONNECTION_KEYS = frozenset({"ADDRESS", "NAMESPACE", "TLS"})
# Consumed by the scheduler; accepted here so it is not treated as a typo.
_IGNORED_KEYS = frozenset({"SCHEDULES"})


@dataclass(frozen=True, slots=True)
class TemporalOptions:
    """Connection settings for one Django task backend alias."""

    address: str
    namespace: str
    tls: bool

    @classmethod
    def from_mapping(cls, options: Mapping[str, Any]) -> "TemporalOptions":
        """Build options from a ``TASKS`` OPTIONS mapping, applying defaults."""
        unsupported = sorted(set(options) - _CONNECTION_KEYS - _IGNORED_KEYS)
        if unsupported:
            raise ImproperlyConfigured(
                "Unsupported option(s) for the Temporal task backend: "
                f"{', '.join(unsupported)}. Supported options are "
                f"{', '.join(sorted(_CONNECTION_KEYS))} and "
                f"{', '.join(sorted(_IGNORED_KEYS))}."
            )

        address = options.get("ADDRESS", DEFAULT_ADDRESS)
        if not isinstance(address, str) or not address:
            raise ImproperlyConfigured(
                "The Temporal task backend ADDRESS option must be a non-empty "
                f"string, got {address!r}."
            )

        namespace = options.get("NAMESPACE", DEFAULT_NAMESPACE)
        if not isinstance(namespace, str) or not namespace:
            raise ImproperlyConfigured(
                "The Temporal task backend NAMESPACE option must be a non-empty "
                f"string, got {namespace!r}."
            )

        tls = options.get("TLS", DEFAULT_TLS)
        if not isinstance(tls, bool):
            raise ImproperlyConfigured(
                f"The Temporal task backend TLS option must be a boolean, got {tls!r}."
            )

        return cls(address=address, namespace=namespace, tls=tls)


def get_options(alias: str) -> TemporalOptions:
    """Return the Temporal connection options configured for ``alias``."""
    return TemporalOptions.from_mapping(task_backends[alias].options)


# Clients are bound to the event loop that created them. Sync callers go
# through ``async_to_sync``, which runs each call on a fresh loop, so the cache
# is keyed by loop: async callers reuse one client, sync callers reconnect.
_CLIENTS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[tuple[str, str, bool], temporalio.client.Client]
] = weakref.WeakKeyDictionary()


def _prune_closed_loops() -> None:
    # A closed loop must never be reused, and a stale client keeps the closed
    # loop reachable, which would otherwise defeat the weak key cache.
    for loop in [loop for loop in _CLIENTS if loop.is_closed()]:
        del _CLIENTS[loop]


async def connect(options: TemporalOptions) -> temporalio.client.Client:
    """Return a client for ``options`` in the running event loop."""
    loop = asyncio.get_running_loop()
    _prune_closed_loops()

    cache = _CLIENTS.get(loop)
    if cache is None:
        cache = {}
        _CLIENTS[loop] = cache

    key = (options.address, options.namespace, options.tls)
    client = cache.get(key)
    if client is None:
        client = await temporalio.client.Client.connect(
            options.address,
            namespace=options.namespace,
            tls=True if options.tls else None,
        )
        cache[key] = client
    return client
