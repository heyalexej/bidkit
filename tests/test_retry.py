from __future__ import annotations

import asyncio

import httpx
import pytest

from bidkit import AsyncEbayClient, EbayAPIError, EbayClient, EbayConfig
from bidkit.retry import (
    compute_delay,
    should_retry_exception,
    should_retry_status,
)

# A synthetic service lets us drive POST/GET through the transport without a typed
# generated method, so we can isolate the retry/method-awareness logic.
SERVICE = {"base_path": "/sell/inventory/v1", "subdomain": "api"}


def _client(handler, *, max_retries: int) -> EbayClient:
    # retry_backoff=0.0 makes the jittered delay deterministically 0 so tests never sleep.
    return EbayClient(
        EbayConfig(
            access_token="token",
            marketplace_id="EBAY_DE",
            max_retries=max_retries,
            retry_backoff=0.0,
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _post(client: EbayClient, **kwargs):
    return client.request(service=SERVICE, operation_id="op", method="POST", path="/op", **kwargs)


def test_retries_transient_5xx_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"itemId": "v1|1|0"})

    item = _client(handler, max_retries=3).buy.browse.get_item("v1|1|0")
    assert item.item_id == "v1|1|0"
    assert calls["n"] == 3


def test_retries_429_for_non_idempotent_post() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, json={})
        return httpx.Response(200, json={})

    # 429 is safe to replay even for POST: the request was rejected before processing.
    _post(_client(handler, max_retries=2), raw_response=True)
    assert calls["n"] == 2


def test_does_not_retry_5xx_for_post() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    with pytest.raises(EbayAPIError) as exc:
        _post(_client(handler, max_retries=3))
    assert exc.value.status_code == 503
    assert calls["n"] == 1  # POST + 5xx is not replayed


def test_retries_are_exhausted_and_surface_last_error() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    with pytest.raises(EbayAPIError) as exc:
        _client(handler, max_retries=2).buy.browse.get_item("v1|1|0")
    assert exc.value.status_code == 503
    assert calls["n"] == 3  # initial + 2 retries


def test_retry_disabled_when_max_retries_zero() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    with pytest.raises(EbayAPIError):
        _client(handler, max_retries=0).buy.browse.get_item("v1|1|0")
    assert calls["n"] == 1


def test_async_client_retries_transient_5xx() -> None:
    async def run() -> None:
        calls = {"n": 0}

        async def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] < 2:
                return httpx.Response(500)
            return httpx.Response(200, json={"itemId": "v1|2|0"})

        client = AsyncEbayClient(
            EbayConfig(access_token="token", max_retries=3, retry_backoff=0.0),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        try:
            item = await client.buy.browse.get_item("v1|2|0")
        finally:
            await client.close()
        assert item.item_id == "v1|2|0"
        assert calls["n"] == 2

    asyncio.run(run())


def test_compute_delay_honors_retry_after_header() -> None:
    config = EbayConfig(retry_max_backoff=60.0)
    response = httpx.Response(429, headers={"retry-after": "12"})
    assert compute_delay(0, response, config) == 12.0

    # Retry-After above the cap is clamped.
    capped = httpx.Response(429, headers={"retry-after": "600"})
    assert compute_delay(0, capped, config) == 60.0


def test_retry_predicates() -> None:
    config = EbayConfig()
    assert should_retry_status("GET", 503, config) is True
    assert should_retry_status("POST", 503, config) is False
    assert should_retry_status("POST", 429, config) is True
    assert should_retry_status("GET", 404, config) is False
    assert should_retry_exception("GET") is True
    assert should_retry_exception("POST") is False
