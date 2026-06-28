from __future__ import annotations

import asyncio
import inspect
from typing import assert_type

import httpx

from ebay_sdk import AsyncEbayClient, EbayClient
from ebay_sdk.config import EbayConfig
from ebay_sdk.generated.models.buy_browse import Item
from ebay_sdk.generated.models.case import CaseSearchResponse
from ebay_sdk.generated.models.sell_inventory import InventoryItems, Offers


def test_generated_namespaces_are_installed() -> None:
    client = EbayClient(EbayConfig(access_token="token"), http_client=_mock_client({}))

    assert client.buy.browse.__class__.__name__ == "BuyBrowseResource"
    assert client.buy.marketplace_insights.__class__.__name__ == "BuyMarketplaceInsightsResource"
    assert client.commerce.feedback.__class__.__name__ == "CommerceFeedbackResource"
    assert client.commerce.media.__class__.__name__ == "CommerceMediaResource"
    assert client.post_order.return_.__class__.__name__ == "ReturnResource"
    assert client.sell.account.__class__.__name__ == "SellAccountV1Resource"
    assert client.sell.account_v2.__class__.__name__ == "SellAccountV2Resource"


def test_get_item_builds_request_and_parses_model() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"itemId": "v1|1|0", "title": "Test item"})

    client = EbayClient(
        EbayConfig(access_token="token", marketplace_id="EBAY_DE"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    item = client.buy.browse.get_item("v1|1|0")
    assert_type(item, Item)
    raw = client.buy.browse.get_item("v1|1|0", raw_response=True)
    assert_type(raw, httpx.Response)

    assert isinstance(item, Item)
    assert item.item_id == "v1|1|0"
    assert item.title == "Test item"
    assert raw.status_code == 200
    assert seen[0].method == "GET"
    assert seen[0].url.raw_path == b"/buy/browse/v1/item/v1%7C1%7C0"
    assert seen[0].headers["authorization"] == "Bearer token"
    assert seen[0].headers["x-ebay-c-marketplace-id"] == "EBAY_DE"


def test_feedback_query_uses_generated_feedback_api() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"feedbackEntries": [{"feedbackId": "fb-1"}]})

    client = EbayClient(
        EbayConfig(access_token="token"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.commerce.feedback.get_feedback(
        user_id="seller",
        feedback_type="FEEDBACK_RECEIVED",
    )

    feedback_entries = response.feedback_entries
    assert feedback_entries is not None
    assert feedback_entries[0].feedback_id == "fb-1"
    assert seen[0].url.path == "/commerce/feedback/v1/feedback"
    assert dict(seen[0].url.params) == {
        "feedback_type": "FEEDBACK_RECEIVED",
        "user_id": "seller",
    }


def test_media_upload_uses_apim_subdomain_and_binary_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    client = EbayClient(
        EbayConfig(access_token="token"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.commerce.media.upload_video(
        "video-1",
        body=b"video-bytes",
    )
    assert_type(result, None)

    assert result is None
    assert seen[0].url.host == "apim.ebay.com"
    assert seen[0].url.path == "/commerce/media/v1_beta/video/video-1/upload"
    assert seen[0].headers["content-type"] == "application/octet-stream"
    assert seen[0].content == b"video-bytes"


def test_media_image_upload_uses_multipart_file_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            201,
            json={
                "expirationDate": "2026-07-28T00:00:00.000Z",
                "imageUrl": "https://i.ebayimg.com/images/test/s-l1600.jpg",
                "maxDimensionImageUrl": "https://i.ebayimg.com/images/test/s-l1600.jpg",
            },
        )

    client = EbayClient(
        EbayConfig(access_token="token"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.commerce.media.create_image_from_file(
        files={"image": ("sample.jpg", b"jpeg-bytes", "image/jpeg")},
    )

    assert result.image_url == "https://i.ebayimg.com/images/test/s-l1600.jpg"
    assert seen[0].url.host == "apim.ebay.com"
    assert seen[0].url.path == "/commerce/media/v1_beta/image/create_image_from_file"
    assert "multipart/form-data" in seen[0].headers["content-type"]
    assert b'name="image"; filename="sample.jpg"' in seen[0].content


def test_post_order_uses_token_auth_and_typed_search_params() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "members": [{"caseId": 5381706738, "buyer": "buyer"}],
                "totalNumberOfCases": 1,
                "paginationOutput": {"limit": 1, "offset": 0},
            },
        )

    client = EbayClient(
        EbayConfig(access_token="token", marketplace_id="EBAY_DE"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.post_order.case.search(limit=1, case_status_filter="CS_CLOSED")
    assert_type(response, CaseSearchResponse)
    raw = client.post_order.case.search(limit=1, raw_response=True)
    assert_type(raw, httpx.Response)

    assert response.members is not None
    assert response.members[0].case_id == 5381706738
    assert raw.status_code == 200
    assert seen[0].headers["authorization"] == "TOKEN token"
    assert seen[0].url.path == "/post-order/v2/casemanagement/search"
    assert dict(seen[0].url.params) == {
        "case_status_filter": "CS_CLOSED",
        "limit": "1",
    }


def test_inventory_aspects_accept_live_mapping_shape() -> None:
    payload = {
        "inventoryItems": [
            {
                "sku": "10010350",
                "product": {
                    "title": "Valvo 4676",
                    "aspects": {
                        "Marke": ["Valvo"],
                        "SKU": ["10010350"],
                    },
                },
            },
        ],
    }

    inventory_items = InventoryItems.model_validate(payload)
    item = inventory_items.inventory_items[0] if inventory_items.inventory_items else None

    assert item is not None
    assert item.product is not None
    assert item.product.aspects == {
        "Marke": ["Valvo"],
        "SKU": ["10010350"],
    }


def test_get_offers_requires_sku_and_keeps_sku_query_param() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "offers": [{"offerId": "1074290655016", "sku": "10010350"}],
                "total": 1,
            },
        )

    client = EbayClient(
        EbayConfig(access_token="token", marketplace_id="EBAY_DE"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    signature = inspect.signature(client.sell.inventory.get_offers)
    assert signature.parameters["sku"].default is inspect.Parameter.empty

    offers = client.sell.inventory.get_offers(sku="10010350", limit="2")
    assert_type(offers, Offers)

    assert offers.offers is not None
    assert offers.offers[0].offer_id == "1074290655016"
    assert dict(seen[0].url.params) == {
        "limit": "2",
        "sku": "10010350",
    }


def test_binary_download_returns_bytes() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=b"%PDF-1.7",
            headers={"content-type": "application/pdf"},
        )

    client = EbayClient(
        EbayConfig(access_token="token"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    payload = client.sell.logistics.download_label_file("shipment-1", accept="application/pdf")
    assert_type(payload, bytes)
    raw = client.sell.logistics.download_label_file(
        "shipment-1",
        accept="application/pdf",
        raw_response=True,
    )
    assert_type(raw, httpx.Response)
    with client.sell.logistics.stream_download_label_file(
        "shipment-1",
        accept="application/pdf",
    ) as response:
        assert_type(response, httpx.Response)
        streamed = response.read()

    assert payload == b"%PDF-1.7"
    assert streamed == b"%PDF-1.7"
    assert raw.status_code == 200
    assert seen[-1].url.path == "/sell/logistics/v1_beta/shipment/shipment-1/download_label_file"
    assert seen[-1].headers["accept"] == "application/pdf"


def test_async_client_uses_same_generated_surface() -> None:
    async def run() -> None:
        seen: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            if request.url.path.endswith("/download_label_file"):
                return httpx.Response(
                    200,
                    content=b"%PDF-async",
                    headers={"content-type": "application/pdf"},
                )
            return httpx.Response(200, json={"itemId": "v1|2|0"})

        client = AsyncEbayClient(
            EbayConfig(access_token="token"),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        try:
            item = await client.buy.browse.get_item("v1|2|0")
            assert_type(item, Item)
            raw = await client.buy.browse.get_item("v1|2|0", raw_response=True)
            assert_type(raw, httpx.Response)
            async with client.sell.logistics.stream_download_label_file(
                "shipment-2",
                accept="application/pdf",
            ) as response:
                assert_type(response, httpx.Response)
                streamed = await response.aread()
        finally:
            await client.close()

        assert item.item_id == "v1|2|0"
        assert streamed == b"%PDF-async"
        assert raw.status_code == 200
        assert seen[0].headers["authorization"] == "Bearer token"

    asyncio.run(run())


def _mock_client(payload: dict[str, object]) -> httpx.Client:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))
