"""Search eBay listings with the Browse API.

Needs only application credentials (client-credentials grant):

    EBAY_APP_ID=... EBAY_CERT_ID=... uv run examples/search_items.py "vintage radio"
"""

from __future__ import annotations

import sys

from bidkit import EbayClient, EbayConfig


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "vintage radio"
    with EbayClient(EbayConfig.from_env()) as client:
        results = client.buy.browse.search(q=query, limit="10")
        for item in results.item_summaries or []:
            price = f"{item.price.value} {item.price.currency}" if item.price else "?"
            print(f"{price:>14}  {item.title}")


if __name__ == "__main__":
    main()
