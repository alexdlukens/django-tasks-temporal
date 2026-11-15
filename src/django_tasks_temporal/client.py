"""Temporal connection options and client construction.

Options live in ``TASKS[alias]["OPTIONS"]``. Only connection-related keys are
read here; ``SCHEDULES`` and ``ACTIVITY_TIMEOUT`` are consumed by
:mod:`django_tasks_temporal.schedules` and the enqueue path and are ignored
by the parser.
"""

import asyncio
import math
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import temporalio.client
import temporalio.service
from django.core.exceptions import ImproperlyConfigured
from django.tasks import task_backends

from ._shared import DEFAULT_ACTIVITY_TIMEOUT_SECONDS

DEFAULT_ADDRESS = "localhost:7233"
DEFAULT_NAMESPACE = "default"
DEFAULT_TLS = False
# Largest duration Temporal's protobuf Duration can carry (10,000 years).
_MAX_ACTIVITY_TIMEOUT_SECONDS = 10_000 * 365 * 24 * 60 * 60

_CONNECTION_KEYS = frozenset({"ADDRESS", "NAMESPACE", "TLS", "API_KEY"})
# Consumed by the scheduler and the enqueue path; accepted here so it is not
# treated as a typo.
_IGNORED_KEYS = frozenset({"SCHEDULES", "ACTIVITY_TIMEOUT"})
_TLS_KEYS = frozenset(
    {"server_root_ca_cert", "client_cert", "client_private_key", "domain"}
)


@dataclass(frozen=True, slots=True)
class TLSFiles:
    """Paths to TLS material, read when a client connects."""

    server_root_ca_cert: str | None = None
    client_cert: str | None = None
    client_private_key: str | None = None
    domain: str | None = None

    def to_config(self) -> temporalio.service.TLSConfig:
        """Read the configured files and build the SDK TLS configuration."""
        return temporalio.service.TLSConfig(
            server_root_ca_cert=self._read(
                "server_root_ca_cert", self.server_root_ca_cert
            ),
            client_cert=self._read("client_cert", self.client_cert),
            client_private_key=self._read(
                "client_private_key", self.client_private_key
            ),
            domain=self.domain,
        )

    @staticmethod
    def _read(name: str, path: str | None) -> bytes | None:
        if path is None:
            return None
        try:
            return Path(path).read_bytes()
        except OSError as exc:
            raise ImproperlyConfigured(
                "The Temporal task backend TLS option "
                f"{name!r} could not read {path!r}: {exc}."
            ) from exc


def _parse_tls(value: Any, *, api_key: str | None) -> bool | TLSFiles:
    """Validate the ``TLS`` option, which is a bool or a certificate mapping."""
    if isinstance(value, bool):
        if not value and api_key is not None:
            raise ImproperlyConfigured(
                "The Temporal task backend API_KEY option requires TLS; "
                "remove TLS: False."
            )
        return value
    if not isinstance(value, Mapping):
        raise ImproperlyConfigured(
            "The Temporal task backend TLS option must be a boolean or a "
            f"mapping, got {value!r}."
        )

    unknown = sorted(set(value) - _TLS_KEYS)
    if unknown:
        raise ImproperlyConfigured(
            "Unsupported TLS option(s) for the Temporal task backend: "
            f"{', '.join(unknown)}. Supported TLS options are "
            f"{', '.join(sorted(_TLS_KEYS))}."
        )

    paths: dict[str, str] = {}
    for name in sorted(_TLS_KEYS):
        raw = value.get(name)
        if raw is None:
            continue
        if not isinstance(raw, str) or not raw:
            raise ImproperlyConfigured(
                f"The Temporal task backend TLS option {name!r} must be a "
                f"non-empty string path, got {raw!r}."
            )
        paths[name] = raw

    if ("client_cert" in paths) != ("client_private_key" in paths):
        raise ImproperlyConfigured(
            "The Temporal task backend TLS options 'client_cert' and "
            "'client_private_key' must be given together."
        )
    return TLSFiles(**paths)


@dataclass(frozen=True, slots=True)
class TemporalOptions:
    """Connection settings for one Django task backend alias."""

    address: str
    namespace: str
    tls: bool | TLSFiles
    api_key: str | None = None

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

        api_key = options.get("API_KEY")
        if api_key is not None and (not isinstance(api_key, str) or not api_key):
            raise ImproperlyConfigured(
                "The Temporal task backend API_KEY option must be a non-empty "
                f"string, got {api_key!r}."
            )

        if "TLS" in options:
            tls = _parse_tls(options["TLS"], api_key=api_key)
        else:
            # An API key is a bearer credential: never send it without TLS.
            tls = True if api_key is not None else DEFAULT_TLS

        return cls(address=address, namespace=namespace, tls=tls, api_key=api_key)


def get_options(alias: str) -> TemporalOptions:
    """Return the Temporal connection options configured for ``alias``."""
    return TemporalOptions.from_mapping(task_backends[alias].options)


def _parse_activity_timeout(value: Any) -> float:
    """Validate ``ACTIVITY_TIMEOUT``: a ``timedelta`` or a number of seconds."""
    if isinstance(value, timedelta):
        seconds = value.total_seconds()
    elif isinstance(value, int | float) and not isinstance(value, bool):
        seconds = float(value)
    else:
        seconds = math.nan
    if not 0 < seconds <= _MAX_ACTIVITY_TIMEOUT_SECONDS:
        raise ImproperlyConfigured(
            "The Temporal task backend ACTIVITY_TIMEOUT option must be a positive "
            f"timedelta or number of seconds, got {value!r}."
        )
    return seconds


def get_activity_timeout(alias: str) -> float:
    """Return the activity timeout, in seconds, for tasks run on ``alias``."""
    options = task_backends[alias].options
    if "ACTIVITY_TIMEOUT" not in options:
        return DEFAULT_ACTIVITY_TIMEOUT_SECONDS
    return _parse_activity_timeout(options["ACTIVITY_TIMEOUT"])


# Clients are bound to the event loop that created them. Sync callers go
# through ``async_to_sync``, which runs each call on a fresh loop, so the cache
# is keyed by loop: async callers reuse one client, sync callers reconnect.
_CLIENTS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[TemporalOptions, temporalio.client.Client]
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

    client = cache.get(options)
    if client is None:
        if isinstance(options.tls, TLSFiles):
            tls: bool | temporalio.service.TLSConfig = options.tls.to_config()
        else:
            tls = options.tls
        client = await temporalio.client.Client.connect(
            options.address,
            namespace=options.namespace,
            api_key=options.api_key,
            tls=tls,
        )
        cache[options] = client
    return client
