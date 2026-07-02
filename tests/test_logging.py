import logging

import httpx
import pytest


def _field(record: logging.LogRecord, name: str) -> object:
    """Read a structured `extra` field; they are dynamic attributes on the record."""
    return record.__dict__[name]


def test_requests_are_logged_at_debug_with_structured_fields(
    make_client,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger="bidkit"):
        client = make_client(lambda request: httpx.Response(200, json={}))
        client.buy.browse.get_item("v1|1|0", raw_response=True)

    record = next(r for r in caplog.records if r.name == "bidkit.transport")
    assert record.levelno == logging.DEBUG
    assert _field(record, "operation") == "getItem"
    assert _field(record, "method") == "GET"
    assert _field(record, "status") == 200
    elapsed_ms = _field(record, "elapsed_ms")
    assert isinstance(elapsed_ms, int) and elapsed_ms >= 0
    assert "getItem" in record.getMessage()
    assert "200" in record.getMessage()


def test_nothing_is_logged_by_default(make_client, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="bidkit"):
        client = make_client(lambda request: httpx.Response(200, json={}))
        client.buy.browse.get_item("v1|1|0", raw_response=True)

    assert [r for r in caplog.records if r.name.startswith("bidkit")] == []


def test_status_retry_is_logged_at_warning(make_client, caplog: pytest.LogCaptureFixture) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, json={})

    with caplog.at_level(logging.DEBUG, logger="bidkit"):
        client = make_client(handler)
        client.buy.browse.get_item("v1|1|0", raw_response=True)

    warning = next(r for r in caplog.records if r.name == "bidkit.retry")
    assert warning.levelno == logging.WARNING
    assert _field(warning, "operation") == "getItem"
    assert _field(warning, "attempt") == 1
    assert _field(warning, "max_attempts") == 3
    assert _field(warning, "status") == 429
    assert _field(warning, "reason") == "retry-after"
    assert _field(warning, "delay_s") == 0
    assert "HTTP 429" in warning.getMessage()
    assert "(Retry-After)" in warning.getMessage()


def test_connection_retry_logs_exception_name(
    make_client, caplog: pytest.LogCaptureFixture
) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectTimeout("boom")
        return httpx.Response(200, json={})

    with caplog.at_level(logging.WARNING, logger="bidkit"):
        client = make_client(handler, retry_backoff=0.0)
        client.buy.browse.get_item("v1|1|0", raw_response=True)

    warning = next(r for r in caplog.records if r.name == "bidkit.retry")
    assert _field(warning, "error") == "ConnectTimeout"
    assert "ConnectTimeout" in warning.getMessage()


def test_token_acquisition_logged_at_info_without_leaking_secrets(
    make_client,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(
                200, json={"access_token": "user-token-secret", "expires_in": 7200}
            )
        return httpx.Response(200, json={})

    with caplog.at_level(logging.INFO, logger="bidkit"):
        client = make_client(
            handler,
            access_token=None,
            app_id="app",
            cert_id="cert-secret",
            refresh_token="refresh-token-secret",
        )
        client.buy.browse.get_item("v1|1|0", raw_response=True)

    record = next(r for r in caplog.records if r.name == "bidkit.auth")
    assert record.levelno == logging.INFO
    assert _field(record, "grant") == "user"
    expires_in = _field(record, "expires_in")
    assert isinstance(expires_in, int) and 0 < expires_in <= 7200
    message = record.getMessage()
    assert "refreshed user token" in message
    for secret in ("user-token-secret", "refresh-token-secret", "cert-secret"):
        assert secret not in message
