from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from ebay_sdk import AsyncEbayClient, EbayClient, EbayConfig

TOKEN_RESPONSE = {
    "access_token": "user-access-token",
    "expires_in": 7200,
    "token_type": "User Access Token",
}


def _config(**overrides) -> EbayConfig:
    base = {
        "app_id": "App-Id",
        "cert_id": "Cert-Id",
        "refresh_token": "refresh-token-value",
        "scopes": ("https://api.ebay.com/oauth/api_scope",),
    }
    return EbayConfig.model_validate({**base, **overrides})


def test_sync_concurrent_callers_refresh_once() -> None:
    """N threads hitting a cold cache must trigger a single token refresh, not a stampede."""
    calls = 0
    counter_lock = threading.Lock()

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        with counter_lock:
            calls += 1
        time.sleep(0.02)  # hold the refresh in-flight so other threads pile up on the lock
        return httpx.Response(200, json=TOKEN_RESPONSE)

    client = EbayClient(
        _config(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with ThreadPoolExecutor(max_workers=8) as pool:
        tokens = list(pool.map(lambda _: client.auth.access_token(client.http), range(8)))

    assert calls == 1
    assert tokens == ["user-access-token"] * 8


def test_async_concurrent_callers_refresh_once() -> None:
    """The async path must coalesce concurrent refreshes the same way the sync path does."""

    async def run() -> None:
        calls = 0

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.02)  # yield while the refresh is in-flight
            return httpx.Response(200, json=TOKEN_RESPONSE)

        client = AsyncEbayClient(
            _config(),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

        tokens = await asyncio.gather(
            *(client.auth.async_access_token(client.http) for _ in range(8))
        )

        assert calls == 1
        assert tokens == ["user-access-token"] * 8

    asyncio.run(run())
