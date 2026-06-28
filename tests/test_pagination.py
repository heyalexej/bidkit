from __future__ import annotations

import asyncio

import httpx

from ebay_sdk import AsyncEbayClient, EbayClient, EbayConfig, paginate, paginate_async


def _inventory_handler(pages: dict[str, dict]):
    """Serve inventory pages keyed by the requested offset."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = request.url.params.get("offset", "0")
        seen.append(offset)
        return httpx.Response(200, json=pages[offset])

    return handler, seen


def _client(handler) -> EbayClient:
    return EbayClient(
        EbayConfig(access_token="token", marketplace_id="EBAY_DE"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_paginate_follows_next_url_across_pages() -> None:
    pages = {
        "0": {
            "inventoryItems": [{"sku": "a"}, {"sku": "b"}],
            "total": 3,
            "limit": 2,
            "next": "https://api.ebay.com/sell/inventory/v1/inventory_item?limit=2&offset=2",
        },
        "2": {"inventoryItems": [{"sku": "c"}], "total": 3, "limit": 2},
    }
    handler, seen = _inventory_handler(pages)
    client = _client(handler)

    skus = [item.sku for item in paginate(client.sell.inventory.get_inventory_items, limit="2")]

    assert skus == ["a", "b", "c"]
    assert seen == ["0", "2"]  # second request followed the next URL's offset


def test_paginate_numeric_fallback_without_next_url() -> None:
    # No `next` field; advancement is computed from total/limit/offset.
    pages = {
        "0": {"inventoryItems": [{"sku": "a"}, {"sku": "b"}], "total": 3, "limit": 2, "offset": 0},
        "2": {"inventoryItems": [{"sku": "c"}], "total": 3, "limit": 2, "offset": 2},
    }
    handler, seen = _inventory_handler(pages)
    client = _client(handler)

    skus = [item.sku for item in paginate(client.sell.inventory.get_inventory_items, limit="2")]

    assert skus == ["a", "b", "c"]
    assert seen == ["0", "2"]


def test_paginate_stops_at_max_items() -> None:
    pages = {
        "0": {
            "inventoryItems": [{"sku": "a"}, {"sku": "b"}],
            "total": 10,
            "limit": 2,
            "next": "https://api.ebay.com/sell/inventory/v1/inventory_item?limit=2&offset=2",
        },
    }
    handler, seen = _inventory_handler(pages)
    client = _client(handler)

    skus = [
        item.sku
        for item in paginate(client.sell.inventory.get_inventory_items, limit="2", max_items=1)
    ]

    assert skus == ["a"]
    assert seen == ["0"]  # stopped before requesting the next page


def test_paginate_single_page_without_pagination_metadata() -> None:
    pages = {"0": {"inventoryItems": [{"sku": "only"}]}}
    handler, seen = _inventory_handler(pages)
    client = _client(handler)

    skus = [item.sku for item in paginate(client.sell.inventory.get_inventory_items)]

    assert skus == ["only"]
    assert seen == ["0"]


def test_paginate_follows_nested_pagination_object() -> None:
    # The Feedback API nests paging under a `pagination` object rather than the top level.
    pages = {
        "0": {
            "feedbackEntries": [{"feedbackId": "f1"}, {"feedbackId": "f2"}],
            "pagination": {
                "total": 3,
                "limit": 2,
                "offset": 0,
                "next": "https://api.ebay.com/commerce/feedback/v1/feedback?limit=2&offset=2",
            },
        },
        "2": {
            "feedbackEntries": [{"feedbackId": "f3"}],
            "pagination": {"total": 3, "limit": 2, "offset": 2},
        },
    }
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = request.url.params.get("offset", "0")
        seen.append(offset)
        return httpx.Response(200, json=pages[offset])

    client = _client(handler)
    ids = [
        entry.feedback_id
        for entry in paginate(
            client.commerce.feedback.get_feedback,
            feedback_type="FEEDBACK_RECEIVED",
            user_id="seller",
            limit="2",
        )
    ]

    assert ids == ["f1", "f2", "f3"]
    assert seen == ["0", "2"]


def test_paginate_async_follows_next_url() -> None:
    async def run() -> None:
        pages = {
            "0": {
                "inventoryItems": [{"sku": "a"}],
                "total": 2,
                "limit": 1,
                "next": "https://api.ebay.com/sell/inventory/v1/inventory_item?limit=1&offset=1",
            },
            "1": {"inventoryItems": [{"sku": "b"}], "total": 2, "limit": 1},
        }

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=pages[request.url.params.get("offset", "0")])

        client = AsyncEbayClient(
            EbayConfig(access_token="token"),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        try:
            skus = [
                item.sku
                async for item in paginate_async(
                    client.sell.inventory.get_inventory_items, limit="1"
                )
            ]
        finally:
            await client.close()
        assert skus == ["a", "b"]

    asyncio.run(run())
