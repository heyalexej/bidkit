#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import orjson

SPEC_MAP = {
    "account-api-v1.json": "sell_account_v1_oas3.json",
    "account-api-v2.json": "sell_account_v2_oas3.json",
    "analytics-api.json": "sell_analytics_v1_oas3.json",
    "browse-api.json": "buy_browse_v1_oas3.json",
    "buy-feed-api.json": "buy_feed_v1_beta_oas3.json",
    "buy-marketing-api.json": "buy_marketing_v1_beta_oas3.json",
    "catalog-api.json": "commerce_catalog_v1_beta_oas3.json",
    "charity-api.json": "commerce_charity_v1_oas3.json",
    "client-registration-api.json": "developer_client_registration_v1_oas3.json",
    "deal-api.json": "buy_deal_v1_oas3.json",
    "developer-analytics-api.json": "developer_analytics_v1_beta_oas3.json",
    "edelivery-international-shipping-api.json": (
        "sell_edelivery_international_shipping_v1_oas3.json"
    ),
    "feed-api.json": "sell_feed_v1_oas3.json",
    "feed-beta-api.json": "buy_feed_v1_beta_oas3.json",
    "feedback-api.json": "commerce_feedback_v1_beta_oas3.json",
    "finances-api.json": "sell_finances_v1_oas3.json",
    "fulfillment-api.json": "sell_fulfillment_v1_oas3.json",
    "identity-api.json": "commerce_identity_v1_oas3.json",
    "inventory-api.json": "sell_inventory_v1_oas3.json",
    "key-management-api.json": "developer_key_management_v1_oas3.json",
    "leads-api.json": "sell_leads_v1_oas3.json",
    "logistics-api.json": "sell_logistics_v1_oas3.json",
    "marketing-api.json": "sell_marketing_v1_oas3.json",
    "marketing-beta-api.json": "buy_marketplace_insights_v1_beta_oas3.json",
    "media-api.json": "commerce_media_v1_beta_oas3.json",
    "message-api.json": "commerce_message_v1_oas3.json",
    "metadata-api.json": "sell_metadata_v1_oas3.json",
    "negotiation-api.json": "sell_negotiation_v1_oas3.json",
    "notification-api.json": "commerce_notification_v1_oas3.json",
    "offer-api.json": "buy_offer_v1_beta_oas3.json",
    "order-v2-api.json": "buy_order_v1_beta_oas3.json",
    "recommendation-api.json": "sell_recommendation_v1_oas3.json",
    "stores-api.json": "sell_stores_v1_oas3.json",
    "taxonomy-api.json": "commerce_taxonomy_v1_oas3.json",
    "translation-api.json": "commerce_translation_v1_beta_oas3.json",
    "vero-public-apis.json": "commerce_vero_v1_oas3.json",
}

GRAPHQL_MAP = {
    "eBay-Graph.graphqls": "inventory_mapping.graphqls",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path("../ebay-api/.playwright-cli"),
        help="Directory containing eBay portal downloads.",
    )
    parser.add_argument(
        "--spec-dir",
        type=Path,
        default=Path("specs/ebay"),
        help="SDK OpenAPI spec directory.",
    )
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    spec_dir = args.spec_dir.resolve()
    graphql_dir = spec_dir / "graphql"
    spec_dir.mkdir(parents=True, exist_ok=True)
    graphql_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for source_name, target_name in sorted(SPEC_MAP.items()):
        source = source_dir / source_name
        target = spec_dir / target_name
        if not source.exists():
            raise FileNotFoundError(f"Missing portal spec: {source}")
        spec = orjson.loads(source.read_bytes())
        shutil.copyfile(source, target)
        copied += 1
        version = spec.get("info", {}).get("version", "")
        path_count = len(spec.get("paths") or {})
        print(f"Copied {source_name} -> {target_name} ({version}, {path_count} paths)", flush=True)

    for source_name, target_name in sorted(GRAPHQL_MAP.items()):
        source = source_dir / source_name
        target = graphql_dir / target_name
        if source.exists():
            shutil.copyfile(source, target)
            print(f"Copied {source_name} -> graphql/{target_name}", flush=True)

    print(f"Synced {copied} OpenAPI specs from {source_dir}", flush=True)


if __name__ == "__main__":
    main()
