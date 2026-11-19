"""Unit tests for connection options and client construction.

These never reach a Temporal server: the SDK connect method is replaced with
an async fake that records its arguments.
"""

import asyncio
import math
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import temporalio.client
import temporalio.service
from django.core.exceptions import ImproperlyConfigured

from django_tasks_temporal import client as client_module
from django_tasks_temporal.client import TemporalOptions, TLSFiles, connect


class _FakeClient:
    """Stand-in for a connected Temporal client."""


@pytest.fixture(autouse=True)
def _clear_client_cache() -> Iterator[None]:
    client_module._CLIENTS.clear()
    yield
    client_module._CLIENTS.clear()


@pytest.fixture
def sdk_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[dict[str, Any]], list[_FakeClient]]:
    calls: list[dict[str, Any]] = []
    clients: list[_FakeClient] = []

    async def fake_connect(target_host: str, **kwargs: Any) -> _FakeClient:
        calls.append({"target_host": target_host, **kwargs})
        client = _FakeClient()
        clients.append(client)
        return client

    monkeypatch.setattr(temporalio.client.Client, "connect", fake_connect)
    return calls, clients


def test_from_mapping_defaults() -> None:
    assert TemporalOptions.from_mapping({}) == TemporalOptions(
        address="localhost:7233",
        namespace="default",
        tls=False,
        api_key=None,
    )


@pytest.mark.parametrize("value", ["", 123, b"secret"])
def test_api_key_must_be_non_empty_string(value: Any) -> None:
    with pytest.raises(ImproperlyConfigured, match="API_KEY"):
        TemporalOptions.from_mapping({"API_KEY": value})


def test_tls_boolean_still_accepted() -> None:
    assert TemporalOptions.from_mapping({"TLS": True}).tls is True
    assert TemporalOptions.from_mapping({"TLS": False}).tls is False


def test_tls_rejects_other_types() -> None:
    with pytest.raises(ImproperlyConfigured, match="boolean or a mapping"):
        TemporalOptions.from_mapping({"TLS": "yes"})


def test_tls_mapping_parses_paths() -> None:
    options = TemporalOptions.from_mapping(
        {
            "TLS": {
                "server_root_ca_cert": "/certs/ca.pem",
                "client_cert": "/certs/client.pem",
                "client_private_key": "/certs/client-key.pem",
                "domain": "temporal.example.com",
            }
        }
    )

    assert options.tls == TLSFiles(
        server_root_ca_cert="/certs/ca.pem",
        client_cert="/certs/client.pem",
        client_private_key="/certs/client-key.pem",
        domain="temporal.example.com",
    )


@pytest.mark.parametrize(
    ("tls", "message"),
    [
        ({"client_cert": "/certs/client.pem"}, "given together"),
        ({"client_private_key": "/certs/key.pem"}, "given together"),
        (
            {
                "client_cert": "/certs/client.pem",
                "client_private_key": "/key",
                "ca": "x",
            },
            "Unsupported TLS option",
        ),
        ({"server_root_ca_cert": 3}, "non-empty string path"),
        ({"domain": ""}, "non-empty string path"),
    ],
)
def test_tls_mapping_validation(tls: dict[str, Any], message: str) -> None:
    with pytest.raises(ImproperlyConfigured, match=message):
        TemporalOptions.from_mapping({"TLS": tls})


@pytest.mark.parametrize(
    "address", ["http://localhost:7233", "https://temporal.example.com:7233"]
)
def test_address_rejects_url_schemes(address: str) -> None:
    with pytest.raises(ImproperlyConfigured, match="without a URL scheme"):
        TemporalOptions.from_mapping({"ADDRESS": address})


def test_api_key_is_not_echoed_in_validation_errors() -> None:
    with pytest.raises(ImproperlyConfigured) as exc_info:
        TemporalOptions.from_mapping({"API_KEY": b"super-secret"})

    assert "super-secret" not in str(exc_info.value)


def test_api_key_is_hidden_from_repr() -> None:
    options = TemporalOptions.from_mapping({"API_KEY": "super-secret"})

    assert "super-secret" not in repr(options)
    assert options.api_key == "super-secret"


def test_api_key_enables_tls() -> None:
    options = TemporalOptions.from_mapping({"API_KEY": "secret"})

    assert options.api_key == "secret"
    assert options.tls is True


def test_web_ui_url_is_optional() -> None:
    assert TemporalOptions.from_mapping({}).web_ui_url is None


def test_web_ui_url_trailing_slash_is_removed() -> None:
    options = TemporalOptions.from_mapping(
        {"WEB_UI_URL": "https://temporal.example.com/ui/"}
    )

    assert options.web_ui_url == "https://temporal.example.com/ui"


@pytest.mark.parametrize(
    "value",
    ["", "temporal.example.com", "/temporal", "javascript:alert(1)", 1],
)
def test_web_ui_url_must_be_http_url(value: Any) -> None:
    with pytest.raises(ImproperlyConfigured, match="WEB_UI_URL"):
        TemporalOptions.from_mapping({"WEB_UI_URL": value})


def test_api_key_rejects_explicitly_disabled_tls() -> None:
    with pytest.raises(ImproperlyConfigured, match="requires TLS"):
        TemporalOptions.from_mapping({"API_KEY": "secret", "TLS": False})


def test_connect_passes_api_key_and_tls(
    sdk_connect: tuple[list[dict[str, Any]], list[_FakeClient]],
) -> None:
    calls, clients = sdk_connect
    options = TemporalOptions.from_mapping(
        {
            "ADDRESS": "cloud.temporal.io:7233",
            "NAMESPACE": "ns",
            "API_KEY": "secret",
        }
    )

    client = asyncio.run(connect(options))

    assert client is clients[0]
    assert calls == [
        {
            "target_host": "cloud.temporal.io:7233",
            "namespace": "ns",
            "api_key": "secret",
            "tls": True,
        }
    ]


def test_connect_reads_tls_files(
    tmp_path: Path,
    sdk_connect: tuple[list[dict[str, Any]], list[_FakeClient]],
) -> None:
    calls, _ = sdk_connect
    ca = tmp_path / "ca.pem"
    ca.write_bytes(b"ca-bytes")
    cert = tmp_path / "client.pem"
    cert.write_bytes(b"cert-bytes")
    key = tmp_path / "client-key.pem"
    key.write_bytes(b"key-bytes")
    options = TemporalOptions.from_mapping(
        {
            "TLS": {
                "server_root_ca_cert": str(ca),
                "client_cert": str(cert),
                "client_private_key": str(key),
                "domain": "temporal.example.com",
            }
        }
    )

    asyncio.run(connect(options))

    (call,) = calls
    tls = call["tls"]
    assert isinstance(tls, temporalio.service.TLSConfig)
    assert tls == temporalio.service.TLSConfig(
        server_root_ca_cert=b"ca-bytes",
        client_cert=b"cert-bytes",
        client_private_key=b"key-bytes",
        domain="temporal.example.com",
    )


def test_connect_missing_tls_file(
    tmp_path: Path,
    sdk_connect: tuple[list[dict[str, Any]], list[_FakeClient]],
) -> None:
    calls, _ = sdk_connect
    missing = tmp_path / "missing.pem"
    options = TemporalOptions.from_mapping(
        {"TLS": {"server_root_ca_cert": str(missing)}}
    )

    with pytest.raises(ImproperlyConfigured, match="server_root_ca_cert"):
        asyncio.run(connect(options))

    assert calls == []


def test_connect_caches_by_full_options(
    sdk_connect: tuple[list[dict[str, Any]], list[_FakeClient]],
) -> None:
    calls, _ = sdk_connect

    async def run() -> tuple[_FakeClient, _FakeClient, _FakeClient, _FakeClient]:
        first = await connect(
            TemporalOptions.from_mapping({"ADDRESS": "one:1", "API_KEY": "a"})
        )
        same = await connect(
            TemporalOptions.from_mapping({"ADDRESS": "one:1", "API_KEY": "a"})
        )
        other_key = await connect(
            TemporalOptions.from_mapping({"ADDRESS": "one:1", "API_KEY": "b"})
        )
        other_address = await connect(
            TemporalOptions.from_mapping({"ADDRESS": "two:2"})
        )
        return first, same, other_key, other_address

    first, same, other_key, other_address = asyncio.run(run())

    assert first is same
    assert first is not other_key
    assert first is not other_address
    assert other_key is not other_address
    assert len(calls) == 3


@pytest.mark.parametrize(
    ("value", "seconds"),
    [(timedelta(minutes=2), 120.0), (90, 90.0), (0.5, 0.5)],
)
def test_activity_timeout_accepts_timedelta_or_seconds(
    value: Any, seconds: float
) -> None:
    assert client_module._parse_activity_timeout(value) == seconds


@pytest.mark.parametrize(
    "value", [0, -1, True, "1h", math.inf, timedelta(0), timedelta.max]
)
def test_activity_timeout_rejects_invalid_values(value: Any) -> None:
    with pytest.raises(ImproperlyConfigured, match="ACTIVITY_TIMEOUT"):
        client_module._parse_activity_timeout(value)
