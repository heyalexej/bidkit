"""Fetch inventory items concurrently with the async client.

Needs a user refresh token with the inventory scope:

    EBAY_APP_ID=... EBAY_CERT_ID=... EBAY_REFRESH_TOKEN=... uv run examples/async_inventory.py
"""

from __future__ import annotations

import asyncio

from bidkit import AsyncEbayClient, EbayConfig, paginate_async


async def main() -> None:
    async with AsyncEbayClient(EbayConfig.from_env()) as client:
        async for item in paginate_async(
            client.sell.inventory.get_inventory_items, limit="100", max_items=300
        ):
            title = item.product.title if item.product else "?"
            print(f"{item.sku}  {title}")


if __name__ == "__main__":
    asyncio.run(main())
