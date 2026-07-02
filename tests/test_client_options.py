import httpx
import pytest
from pydantic import ValidationError

from bidkit import EbayAPIError, EbayClient, EbayConfig


def _client(handler, **config_kwargs) -> EbayClient:
    config_kwargs.setdefault("access_token", "token")
    return EbayClient(
        EbayConfig(**config_kwargs),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_with_options_overrides_retries_without_touching_the_base_client() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(429, headers={"retry-after": "0"})

    client = _client(handler, max_retries=1)

    with pytest.raises(EbayAPIError):
        client.with_options(max_retries=0).buy.browse.get_item("v1|1|0")
    assert len(requests) == 1  # no retry on the override client

    requests.clear()
    with pytest.raises(EbayAPIError):
        client.buy.browse.get_item("v1|1|0")
    assert len(requests) == 2  # base client still retries once


def test_with_options_timeout_applies_per_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = _client(handler)
    client.with_options(timeout=7.5).buy.browse.get_item("v1|1|0", raw_response=True)
    client.buy.browse.get_item("v1|1|0", raw_response=True)

    override = {"connect": 7.5, "read": 7.5, "write": 7.5, "pool": 7.5}
    assert seen[0].extensions["timeout"] == override
    # The base client keeps the httpx client's own default (no per-request override).
    assert seen[1].extensions.get("timeout") != override


def test_round_tripped_config_does_not_clobber_injected_client_timeout() -> None:
    """Serializing a config (model_dump/validate) must not turn the timeout default
    into a per-request override that beats an injected client's own timeout."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    original = EbayConfig(access_token="token")
    round_tripped = EbayConfig(**original.model_dump())
    client = EbayClient(
        round_tripped,
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler),
            timeout=httpx.Timeout(connect=2.0, read=120.0, write=10.0, pool=5.0),
        ),
    )
    client.buy.browse.get_item("v1|1|0", raw_response=True)

    assert "timeout" not in seen[0].extensions or seen[0].extensions["timeout"] == {
        "connect": 2.0,
        "read": 120.0,
        "write": 10.0,
        "pool": 5.0,
    }


def test_with_options_overrides_marketplace_header() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = _client(handler, marketplace_id="EBAY_DE")
    client.with_options(marketplace_id="EBAY_US").buy.browse.get_item("v1|1|0", raw_response=True)

    assert seen[0].headers["x-ebay-c-marketplace-id"] == "EBAY_US"
    assert client.config.marketplace_id == "EBAY_DE"


def test_with_options_shares_token_cache_and_http_client() -> None:
    token_requests = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            token_requests["n"] += 1
            return httpx.Response(200, json={"access_token": "minted", "expires_in": 7200})
        return httpx.Response(200, json={})

    client = EbayClient(
        EbayConfig(app_id="app", cert_id="cert", refresh_token="refresh"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    scoped = client.with_options(max_retries=0)

    client.buy.browse.get_item("v1|1|0", raw_response=True)
    scoped.buy.browse.get_item("v1|1|0", raw_response=True)

    assert token_requests["n"] == 1
    assert scoped.http is client.http


def test_with_options_close_never_closes_the_shared_pool() -> None:
    client = _client(lambda request: httpx.Response(200, json={}))
    scoped = client.with_options(timeout=1.0)

    scoped.close()
    client.buy.browse.get_item("v1|1|0", raw_response=True)  # still usable


def test_with_options_rejects_unknown_fields() -> None:
    client = _client(lambda request: httpx.Response(200, json={}))

    with pytest.raises(ValidationError):
        client.with_options(not_a_field=1)
