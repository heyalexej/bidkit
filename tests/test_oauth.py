from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from bidkit import AsyncEbayClient, EbayClient, EbayConfig, OAuthTokens
from bidkit.errors import EbayConfigError

TOKEN_RESPONSE = {
    "access_token": "user-access-token",
    "expires_in": 7200,
    "refresh_token": "refresh-token-value",
    "refresh_token_expires_in": 47304000,
    "token_type": "User Access Token",
}


def _config(**overrides) -> EbayConfig:
    base = {
        "app_id": "App-Id",
        "cert_id": "Cert-Id",
        "ru_name": "Ru-Name",
        "scopes": ("https://api.ebay.com/oauth/api_scope",),
    }
    return EbayConfig.model_validate({**base, **overrides})


def test_authorization_url_includes_client_and_scopes() -> None:
    client = EbayClient(_config(), http_client=httpx.Client())
    url = client.authorization_url(state="xyz", prompt="login")
    parts = urlsplit(url)
    query = parse_qs(parts.query)

    assert parts.netloc == "auth.ebay.com"
    assert query["client_id"] == ["App-Id"]
    assert query["redirect_uri"] == ["Ru-Name"]
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["https://api.ebay.com/oauth/api_scope"]
    assert query["state"] == ["xyz"]
    assert query["prompt"] == ["login"]


def test_authorization_url_requires_app_id_and_ru_name() -> None:
    client = EbayClient(EbayConfig(app_id="App-Id"), http_client=httpx.Client())
    with pytest.raises(EbayConfigError):
        client.authorization_url()


def test_exchange_code_builds_request_and_parses_tokens() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=TOKEN_RESPONSE)

    client = EbayClient(
        _config(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    tokens = client.exchange_code("auth-code-123")

    assert isinstance(tokens, OAuthTokens)
    assert tokens.access_token == "user-access-token"
    assert tokens.refresh_token == "refresh-token-value"
    assert tokens.refresh_token_expiry is not None and tokens.token_expiry is not None

    request = seen[0]
    assert request.url.path == "/identity/v1/oauth2/token"
    body = parse_qs(request.content.decode())
    assert body["grant_type"] == ["authorization_code"]
    assert body["code"] == ["auth-code-123"]
    assert body["redirect_uri"] == ["Ru-Name"]
    # client_credentials Basic auth header (appId:certId)
    expected = base64.b64encode(b"App-Id:Cert-Id").decode()
    assert request.headers["authorization"] == f"Basic {expected}"


def test_exchange_code_seeds_client_so_next_call_uses_the_access_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(200, json={"itemId": "v1|1|0"})

    client = EbayClient(
        _config(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.exchange_code("auth-code-123")
    # The refresh token is now stored, and the access token is cached: no further token call.
    assert client.config.refresh_token_value == "refresh-token-value"

    captured: list[httpx.Request] = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"itemId": "v1|1|0"})

    client.http = httpx.Client(transport=httpx.MockTransport(capture))
    client._transport.client = client.http
    client.buy.browse.get_item("v1|1|0")
    assert captured[0].headers["authorization"] == "Bearer user-access-token"


def test_exchange_code_override_ru_name() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=TOKEN_RESPONSE)

    client = EbayClient(
        EbayConfig(app_id="App-Id", cert_id="Cert-Id"),  # no ru_name configured
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.exchange_code("code", ru_name="Explicit-Ru")
    assert parse_qs(seen[0].content.decode())["redirect_uri"] == ["Explicit-Ru"]


def test_exchange_code_without_ru_name_raises() -> None:
    client = EbayClient(
        EbayConfig(app_id="App-Id", cert_id="Cert-Id"),
        http_client=httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(200))),
    )
    with pytest.raises(EbayConfigError):
        client.exchange_code("code")


def test_async_exchange_code() -> None:
    import asyncio

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=TOKEN_RESPONSE)

    async def run() -> None:
        client = AsyncEbayClient(
            _config(),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        try:
            tokens = await client.exchange_code("auth-code-123")
        finally:
            await client.close()
        assert tokens.refresh_token == "refresh-token-value"
        assert client.config.refresh_token_value == "refresh-token-value"

    asyncio.run(run())
