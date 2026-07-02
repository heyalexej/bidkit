from __future__ import annotations

import asyncio

import httpx

from bidkit import AsyncEbayClient, EbayClient, EbayConfig
from bidkit.auth import EbayAuth


def _cache_key(**config) -> str:
    return EbayAuth(EbayConfig.model_validate(config))._cache_key()


# --- #1 token cache is tenant-safe ------------------------------------------------------------


def test_cache_key_isolates_by_refresh_token() -> None:
    a = _cache_key(app_id="A", cert_id="C", refresh_token="tok-1")
    b = _cache_key(app_id="A", cert_id="C", refresh_token="tok-2")
    assert a != b


def test_cache_key_isolates_by_app_id() -> None:
    a = _cache_key(app_id="A", cert_id="C", refresh_token="tok")
    b = _cache_key(app_id="B", cert_id="C", refresh_token="tok")
    assert a != b


def test_cache_key_isolates_by_env_and_scopes() -> None:
    base = {"app_id": "A", "cert_id": "C", "refresh_token": "tok"}
    assert _cache_key(**base, sandbox=False) != _cache_key(**base, sandbox=True)
    assert _cache_key(**base, scopes=("s1",)) != _cache_key(**base, scopes=("s2",))


def test_cache_key_is_stable_for_the_same_identity() -> None:
    base = {"app_id": "A", "cert_id": "C", "refresh_token": "tok"}
    assert _cache_key(**base) == _cache_key(**base)


def test_cache_key_does_not_leak_the_refresh_token() -> None:
    key = _cache_key(app_id="A", cert_id="C", refresh_token="super-secret-token")
    assert "super-secret-token" not in key


# --- #6 only close clients the SDK created ----------------------------------------------------


def test_injected_http_client_is_not_closed() -> None:
    http = httpx.Client()
    client = EbayClient(EbayConfig(access_token="t"), http_client=http)
    client.close()
    assert not http.is_closed  # caller still owns it
    http.close()


def test_owned_http_client_is_closed() -> None:
    client = EbayClient(EbayConfig(access_token="t"))
    http = client.http
    client.close()
    assert http.is_closed


def test_async_injected_http_client_is_not_closed() -> None:
    async def run() -> None:
        http = httpx.AsyncClient()
        client = AsyncEbayClient(EbayConfig(access_token="t"), http_client=http)
        await client.close()
        assert not http.is_closed
        await http.aclose()

    asyncio.run(run())


# --- #2 schemaless GET returns the parsed body (typed Any, not None) --------------------------


def test_schemaless_get_returns_parsed_json() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"cancelId": "5381706738", "cancelState": "CLOSED"})

    client = EbayClient(
        EbayConfig(access_token="t", marketplace_id="EBAY_DE"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    # cancellation_oas3 documents a 200 with no schema; the SDK returns the parsed body.
    result = client.post_order.cancellation.get_cancellation("5381706738")
    assert result == {"cancelId": "5381706738", "cancelState": "CLOSED"}
