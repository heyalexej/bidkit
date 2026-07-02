from __future__ import annotations

import asyncio

import httpx

from bidkit import AsyncEbayClient, EbayClient, EbayConfig

# A minimal service descriptor so we can drive the transport directly without a generated method.
SERVICE = {
    "key": "buy_browse",
    "title": "Browse",
    "version": "v1",
    "base_path": "/buy/browse/v1",
    "subdomain": "api",
}


def _config(**overrides) -> EbayConfig:
    base = {
        "app_id": "App-Id",
        "cert_id": "Cert-Id",
        "refresh_token": "refresh-token-value",
        "scopes": ("https://api.ebay.com/oauth/api_scope",),
        # keep the test fast: zero backoff so the retry sleep is instant
        "retry_backoff": 0.0,
        "retry_max_backoff": 0.0,
    }
    return EbayConfig.model_validate({**base, **overrides})


def _make_handler(bearers: list[str | None], state: dict[str, int]):
    """Serve the token endpoint with an ever-incrementing, already-stale token, and the API
    endpoint with one 429 (forcing a retry) then a 200. Records the bearer of each API attempt.
    ``expires_in: 0`` makes every minted token immediately stale, so the per-attempt auth
    re-fetch is forced to refresh and mint the next token."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            state["tokens"] += 1
            return httpx.Response(
                200,
                json={
                    "access_token": f"token-{state['tokens']}",
                    "expires_in": 0,
                    "token_type": "Bearer",
                },
            )
        bearers.append(request.headers.get("authorization"))
        state["api"] += 1
        if state["api"] == 1:
            return httpx.Response(429)  # transient -> retried
        return httpx.Response(200, json={})

    return handler


def test_sync_retry_refetches_auth_after_token_goes_stale() -> None:
    bearers: list[str | None] = []
    state = {"tokens": 0, "api": 0}
    client = EbayClient(
        _config(),
        http_client=httpx.Client(transport=httpx.MockTransport(_make_handler(bearers, state))),
    )

    resp = client._request(
        service=SERVICE, operation_id="getThing", method="GET", path="/item/x", raw_response=True
    )

    assert resp.status_code == 200
    # The retried request must carry a freshly refreshed token, not the stale one from attempt 0.
    assert bearers == ["Bearer token-1", "Bearer token-2"]
    assert state["tokens"] == 2


def test_async_retry_refetches_auth_after_token_goes_stale() -> None:
    async def run() -> None:
        bearers: list[str | None] = []
        state = {"tokens": 0, "api": 0}
        client = AsyncEbayClient(
            _config(),
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(_make_handler(bearers, state))
            ),
        )

        resp = await client._request(
            service=SERVICE,
            operation_id="getThing",
            method="GET",
            path="/item/x",
            raw_response=True,
        )

        assert resp.status_code == 200
        assert bearers == ["Bearer token-1", "Bearer token-2"]
        assert state["tokens"] == 2

    asyncio.run(run())
