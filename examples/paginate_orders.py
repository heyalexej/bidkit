"""Iterate a seller's recent orders across pages with the Fulfillment API.

Needs a user refresh token (mint one with scripts/oauth_login.py):

    EBAY_APP_ID=... EBAY_CERT_ID=... EBAY_REFRESH_TOKEN=... uv run examples/paginate_orders.py
"""

from __future__ import annotations

from bidkit import EbayClient, EbayConfig, paginate


def main() -> None:
    with EbayClient(EbayConfig.from_env()) as client:
        for order in paginate(client.sell.fulfillment.get_orders, limit="50", max_items=200):
            total = order.pricing_summary.total if order.pricing_summary else None
            amount = f"{total.value} {total.currency}" if total else "?"
            print(f"{order.order_id}  {order.order_fulfillment_status}  {amount}")


if __name__ == "__main__":
    main()
