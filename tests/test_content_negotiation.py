from __future__ import annotations

import inspect

import httpx

from ebay_sdk import EbayClient, EbayConfig
from ebay_sdk.generated.models.sell_inventory import BulkEbayOfferDetailsWithKeys


def _client(handler) -> EbayClient:
    return EbayClient(
        EbayConfig(access_token="token", marketplace_id="EBAY_DE"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_json_body_methods_drop_content_negotiation_params() -> None:
    client = _client(lambda _r: httpx.Response(200, json={}))
    params = inspect.signature(client.sell.inventory.bulk_create_offer).parameters
    assert "content_type" not in params
    assert "content_language" not in params


def test_json_post_sets_content_type_automatically() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"responses": []})

    client = _client(handler)
    client.sell.inventory.bulk_create_offer(body=BulkEbayOfferDetailsWithKeys())

    assert seen[0].headers["content-type"] == "application/json"


def test_content_language_comes_from_config() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"responses": []})

    client = EbayClient(
        EbayConfig(access_token="token", marketplace_id="EBAY_DE", content_language="de-DE"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.sell.inventory.bulk_create_offer(body=BulkEbayOfferDetailsWithKeys())

    assert seen[0].headers["content-language"] == "de-DE"


def test_binary_upload_sets_octet_stream() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    client = _client(handler)
    client.commerce.media.upload_video("video-1", body=b"bytes")

    assert seen[0].headers["content-type"] == "application/octet-stream"
