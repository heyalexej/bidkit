#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import mimetypes
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import httpx
import orjson

from bidkit import EbayClient, EbayConfig

TEST_SKU = "DYDYDDYDYDYDABABABABABAAAAAAAAA"
TEST_TITLE = "DYDYDDYDYDYD ABABABABABA AAAAAAAAA"

SENSITIVE_KEYS = {
    "Authorization",
    "accessToken",
    "access_token",
    "addressLine1",
    "addressLine2",
    "auth",
    "buyer",
    "buyerRegistrationAddress",
    "cert_id",
    "client_id",
    "client_secret",
    "email",
    "emailAddress",
    "firstName",
    "fullName",
    "jwe",
    "lastName",
    "phone",
    "phoneNumber",
    "privateKey",
    "privateKeyPem",
    "refreshToken",
    "refresh_token",
    "shippingStep",
    "token",
}


def main() -> None:
    args = parse_args()
    raw = orjson.loads(args.credentials.read_bytes())
    creds = raw.get("credentials", raw)
    scopes = tuple(creds.get("granted_scopes") or creds.get("scopes") or ())
    if isinstance(scopes, str):
        scopes = tuple(scope for scope in scopes.split() if scope)

    config = EbayConfig(
        app_id=creds.get("app_id") or creds.get("client_id"),
        cert_id=creds.get("cert_id") or creds.get("client_secret"),
        dev_id=creds.get("dev_id"),
        ru_name=creds.get("ru_name") or creds.get("redirect_uri"),
        refresh_token=creds.get("refresh_token"),
        scopes=scopes,
        marketplace_id=args.marketplace,
        accept_language=args.language,
        content_language=args.language,
        timeout=args.timeout,
    )

    print(
        f"Progress: live smoke marketplace={args.marketplace} scopes={len(scopes)}",
        flush=True,
    )
    runner = SmokeRunner(dump_responses=args.dump_responses)
    with EbayClient(config) as client:
        run_read_smokes(client, runner, args)
        if args.write_probes:
            run_inventory_probe(client, runner, args)
        if args.media:
            run_media_probe(client, runner, args)

    runner.print_summary()
    if args.strict and runner.has_failures:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live eBay SDK smoke checks.")
    parser.add_argument("--credentials", type=Path, default=Path("/tmp/toktok.json"))
    parser.add_argument("--marketplace", default="EBAY_DE")
    parser.add_argument("--language", default="de-DE")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--image", type=Path, default=Path("/Users/buzz/Desktop/0006617_01.jpg"))
    parser.add_argument("--video", type=Path, default=Path("/Users/buzz/Desktop/0006612.mp4"))
    parser.add_argument("--write-probes", action="store_true")
    parser.add_argument("--keep-inventory-probe", action="store_true")
    parser.add_argument("--media", action="store_true")
    parser.add_argument("--all-probes", action="store_true")
    parser.add_argument("--dump-responses", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    if args.all_probes:
        args.write_probes = True
        args.media = True
    return args


class SmokeRunner:
    def __init__(self, *, dump_responses: bool = False) -> None:
        self.dump_responses = dump_responses
        self.rows: list[dict[str, Any]] = []

    @property
    def has_failures(self) -> bool:
        return any(
            row["status"] == "EXC" or (isinstance(row["status"], int) and row["status"] >= 400)
            for row in self.rows
        )

    def run(
        self,
        label: str,
        call: Callable[[], httpx.Response],
        summarize: Callable[[Any, httpx.Response], Any] | None = None,
    ) -> Any:
        print(f"RUN {label}", flush=True)
        started = time.time()
        try:
            response = call()
            elapsed_ms = round((time.time() - started) * 1000)
            payload = parse_response(response)
            row: dict[str, Any] = {
                "label": label,
                "status": response.status_code,
                "ms": elapsed_ms,
            }
            if response.status_code >= 400:
                row["error"] = compact_error(payload)
                print(f"HTTP {label}: {response.status_code} {row['error']}", flush=True)
            else:
                detail = summarize(payload, response) if summarize else None
                if detail is not None:
                    row["detail"] = detail
                print(
                    f"OK {label}: {response.status_code} {detail if detail is not None else ''}",
                    flush=True,
                )
            if self.dump_responses:
                row["payload"] = scrub(payload)
            self.rows.append(row)
            return payload
        except Exception as exc:
            elapsed_ms = round((time.time() - started) * 1000)
            row = {
                "label": label,
                "status": "EXC",
                "ms": elapsed_ms,
                "error": f"{type(exc).__name__}: {exc}"[:500],
            }
            self.rows.append(row)
            print(f"ERR {label}: {row['error']}", flush=True)
            return None

    def print_summary(self) -> None:
        ok = sum(1 for row in self.rows if isinstance(row["status"], int) and row["status"] < 400)
        http_fail = sum(
            1 for row in self.rows if isinstance(row["status"], int) and row["status"] >= 400
        )
        exc_fail = sum(1 for row in self.rows if row["status"] == "EXC")
        print("\nSMOKE_SUMMARY", flush=True)
        print(
            orjson.dumps(
                {
                    "ok": ok,
                    "http_fail": http_fail,
                    "exceptions": exc_fail,
                    "total": len(self.rows),
                    "pattern_sku": TEST_SKU,
                },
                option=orjson.OPT_INDENT_2,
            ).decode(),
            flush=True,
        )
        print("\nSMOKE_ROWS", flush=True)
        print(orjson.dumps(scrub(self.rows), option=orjson.OPT_INDENT_2).decode(), flush=True)


def run_read_smokes(client: EbayClient, runner: SmokeRunner, args: argparse.Namespace) -> None:
    marketplace = args.marketplace
    language = args.language
    identity = runner.run(
        "commerce.identity.get_user",
        lambda: client.commerce.identity.get_user(raw_response=True),
        lambda p, _r: {
            "username": get(p, "username"),
            "registrationMarketplaceId": get(p, "registrationMarketplaceId"),
        },
    )
    username = get(identity, "username") or "uzagain_com"

    taxonomy = runner.run(
        "commerce.taxonomy.get_default_category_tree_id",
        lambda: client.commerce.taxonomy.get_default_category_tree_id(
            marketplace_id=marketplace,
            raw_response=True,
        ),
        lambda p, _r: scrub(p),
    )
    tree_id = str(get(taxonomy, "categoryTreeId") or "77")
    runner.run(
        "commerce.taxonomy.get_category_tree",
        lambda: client.commerce.taxonomy.get_category_tree(tree_id, raw_response=True),
        lambda p, _r: {
            "treeId": get(p, "categoryTreeId"),
            "rootCategory": get(get(p, "rootCategory", {}), "categoryName"),
        },
    )
    runner.run(
        "commerce.taxonomy.get_category_suggestions",
        lambda: client.commerce.taxonomy.get_category_suggestions(
            category_tree_id=tree_id,
            q="radio",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "categorySuggestions")},
    )

    runner.run(
        "commerce.feedback.get_feedback",
        lambda: client.commerce.feedback.get_feedback(
            user_id=username,
            feedback_type="FEEDBACK_RECEIVED",
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {
            "count": count_key(p, "feedback", "feedbackItems"),
            "total": get(p, "total"),
        },
    )
    runner.run(
        "commerce.feedback.get_feedback_rating_summary",
        lambda: client.commerce.feedback.get_feedback_rating_summary(
            user_id=username,
            filter="ratingType:OVERALL_EXPERIENCE",
            raw_response=True,
        ),
        lambda p, _r: {"ratingSummaries": count_key(p, "ratingSummaryByRatingType")},
    )
    runner.run(
        "commerce.feedback.get_items_awaiting_feedback",
        lambda: client.commerce.feedback.get_items_awaiting_feedback(
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {
            "count": count_key(p, "awaitingFeedback", "items", "feedbackItems"),
            "total": get(p, "total"),
        },
    )

    runner.run(
        "developer.analytics.get_user_rate_limits",
        lambda: client.developer.analytics.get_user_rate_limits(raw_response=True),
        lambda p, _r: {"resources": count_key(p, "apiContext", "rateLimits")},
    )
    runner.run(
        "developer.analytics.get_rate_limits",
        lambda: client.developer.analytics.get_rate_limits(raw_response=True),
        lambda p, _r: {"resources": count_key(p, "apiContext", "rateLimits")},
    )
    runner.run(
        "developer.key_management.get_signing_keys",
        lambda: client.developer.key_management.get_signing_keys(raw_response=True),
        lambda p, _r: {"count": count_key(p, "signingKeys"), "total": get(p, "total")},
    )

    runner.run(
        "sell.account.get_privileges",
        lambda: client.sell.account.get_privileges(raw_response=True),
        lambda p, _r: scrub(p),
    )
    runner.run(
        "sell.account.get_payment_policies",
        lambda: client.sell.account.get_payment_policies(
            marketplace_id=marketplace,
            content_language=language,
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "paymentPolicies"), "total": get(p, "total")},
    )
    runner.run(
        "sell.account.get_return_policies",
        lambda: client.sell.account.get_return_policies(
            marketplace_id=marketplace,
            content_language=language,
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "returnPolicies"), "total": get(p, "total")},
    )
    runner.run(
        "sell.account.get_fulfillment_policies",
        lambda: client.sell.account.get_fulfillment_policies(
            marketplace_id=marketplace,
            content_language=language,
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "fulfillmentPolicies"), "total": get(p, "total")},
    )
    runner.run(
        "sell.account.get_custom_policies",
        lambda: client.sell.account.get_custom_policies(
            policy_types="PRODUCT_COMPLIANCE",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "customPolicies"), "total": get(p, "total")},
    )
    runner.run(
        "sell.account.get_rate_tables",
        lambda: client.sell.account.get_rate_tables(country_code="DE", raw_response=True),
        lambda p, _r: {"count": count_key(p, "rateTables")},
    )
    runner.run(
        "sell.account.get_opted_in_programs",
        lambda: client.sell.account.get_opted_in_programs(raw_response=True),
        lambda p, _r: {"count": count_key(p, "programs")},
    )
    runner.run(
        "sell.account.get_payments_program",
        lambda: client.sell.account.get_payments_program(
            marketplace,
            "EBAY_PAYMENTS",
            raw_response=True,
        ),
        lambda p, _r: {"status": get(p, "status"), "marketplaceId": get(p, "marketplaceId")},
    )
    runner.run(
        "sell.account_v2.get_user_preferences",
        lambda: client.sell.account_v2.get_user_preferences(
            x_ebay_c_marketplace_id=marketplace,
            raw_response=True,
        ),
        lambda p, _r: scrub(p),
    )
    runner.run(
        "sell.account_v2.get_payout_settings",
        lambda: client.sell.account_v2.get_payout_settings(raw_response=True),
        lambda p, _r: scrub(p),
    )

    inventory = runner.run(
        "sell.inventory.get_inventory_items",
        lambda: client.sell.inventory.get_inventory_items(limit="2", raw_response=True),
        lambda p, _r: {"count": count_key(p, "inventoryItems"), "total": get(p, "total")},
    )
    first_item = pick_first(inventory, "inventoryItems")
    first_sku = get(first_item, "sku")
    if first_sku:
        item = runner.run(
            "sell.inventory.get_inventory_item",
            lambda: client.sell.inventory.get_inventory_item(first_sku, raw_response=True),
            lambda p, _r: {
                "sku": get(p, "sku"),
                "condition": get(p, "condition"),
                "title": get(get(p, "product", {}), "title"),
            },
        )
        offers = runner.run(
            "sell.inventory.get_offers",
            lambda: client.sell.inventory.get_offers(
                sku=first_sku,
                marketplace_id=marketplace,
                limit="2",
                raw_response=True,
            ),
            lambda p, _r: {"count": count_key(p, "offers"), "total": get(p, "total")},
        )
        offer = pick_first(offers, "offers")
        offer_id = get(offer, "offerId")
        if offer_id:
            runner.run(
                "sell.inventory.get_offer",
                lambda: client.sell.inventory.get_offer(offer_id, raw_response=True),
                lambda p, _r: {
                    "offerId": get(p, "offerId"),
                    "marketplaceId": get(p, "marketplaceId"),
                    "status": get(p, "status"),
                },
            )
        listing_id = get(offer, "listingId")
        if listing_id:
            runner.run(
                "sell.inventory.get_sku_location_mapping",
                lambda: client.sell.inventory.get_sku_location_mapping(
                    str(listing_id),
                    first_sku,
                    raw_response=True,
                ),
                lambda p, _r: {
                    "listingId": listing_id,
                    "sku": first_sku,
                    "locations": count_key(p, "locations"),
                },
            )
        runner.run(
            "sell.inventory.get_product_compatibility",
            lambda: client.sell.inventory.get_product_compatibility(
                first_sku,
                raw_response=True,
            ),
            lambda p, _r: {"compatibleProducts": count_key(p, "compatibleProducts")},
        )
        args._source_inventory_item = item

    locations = runner.run(
        "sell.inventory.get_inventory_locations",
        lambda: client.sell.inventory.get_inventory_locations(limit="2", raw_response=True),
        lambda p, _r: {"count": count_key(p, "locations"), "total": get(p, "total")},
    )
    location_key = get(pick_first(locations, "locations"), "merchantLocationKey")
    if location_key:
        runner.run(
            "sell.inventory.get_inventory_location",
            lambda: client.sell.inventory.get_inventory_location(location_key, raw_response=True),
            lambda p, _r: {
                "merchantLocationKey": get(p, "merchantLocationKey"),
                "locationStatus": get(p, "locationStatus"),
            },
        )

    orders = runner.run(
        "sell.fulfillment.get_orders",
        lambda: client.sell.fulfillment.get_orders(limit="1", raw_response=True),
        lambda p, _r: {"count": count_key(p, "orders"), "total": get(p, "total")},
    )
    order_id = get(pick_first(orders, "orders"), "orderId")
    if order_id:
        runner.run(
            "sell.fulfillment.get_order",
            lambda: client.sell.fulfillment.get_order(order_id, raw_response=True),
            lambda p, _r: {
                "orderId": get(p, "orderId"),
                "orderFulfillmentStatus": get(p, "orderFulfillmentStatus"),
                "lineItems": count_key(p, "lineItems"),
            },
        )
        runner.run(
            "sell.fulfillment.get_shipping_fulfillments",
            lambda: client.sell.fulfillment.get_shipping_fulfillments(
                order_id,
                raw_response=True,
            ),
            lambda p, _r: {"count": count_key(p, "fulfillments")},
        )
    runner.run(
        "sell.fulfillment.get_payment_dispute_summaries",
        lambda: client.sell.fulfillment.get_payment_dispute_summaries(
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "paymentDisputeSummaries"), "total": get(p, "total")},
    )

    runner.run(
        "sell.feed.get_tasks",
        lambda: client.sell.feed.get_tasks(
            feed_type="LMS_ORDER_REPORT",
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "tasks"), "total": get(p, "total")},
    )
    runner.run(
        "sell.feed.get_order_tasks",
        lambda: client.sell.feed.get_order_tasks(
            feed_type="LMS_ORDER_REPORT",
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "tasks", "orderTasks"), "total": get(p, "total")},
    )
    runner.run(
        "sell.feed.get_inventory_tasks",
        lambda: client.sell.feed.get_inventory_tasks(
            feed_type="LMS_ACTIVE_INVENTORY_REPORT",
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "tasks", "inventoryTasks"), "total": get(p, "total")},
    )
    runner.run(
        "sell.feed.get_schedule_templates",
        lambda: client.sell.feed.get_schedule_templates(
            feed_type="LMS_ORDER_REPORT",
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "scheduleTemplates"), "total": get(p, "total")},
    )
    runner.run(
        "sell.feed.get_schedules",
        lambda: client.sell.feed.get_schedules(
            feed_type="LMS_ORDER_REPORT",
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "schedules"), "total": get(p, "total")},
    )

    campaigns = runner.run(
        "sell.marketing.get_campaigns",
        lambda: client.sell.marketing.get_campaigns(limit="1", raw_response=True),
        lambda p, _r: {"count": count_key(p, "campaigns"), "total": get(p, "total")},
    )
    campaign_id = get(pick_first(campaigns, "campaigns"), "campaignId")
    if campaign_id:
        runner.run(
            "sell.marketing.get_campaign",
            lambda: client.sell.marketing.get_campaign(campaign_id, raw_response=True),
            lambda p, _r: {
                "campaignId": get(p, "campaignId"),
                "status": get(p, "campaignStatus"),
            },
        )
        runner.run(
            "sell.marketing.get_ad_groups",
            lambda: client.sell.marketing.get_ad_groups(
                campaign_id,
                limit="1",
                raw_response=True,
            ),
            lambda p, _r: {"count": count_key(p, "adGroups"), "total": get(p, "total")},
        )
    runner.run(
        "sell.marketing.get_promotions",
        lambda: client.sell.marketing.get_promotions(
            marketplace_id=marketplace,
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "promotions"), "total": get(p, "total")},
    )
    runner.run(
        "sell.marketing.get_report_tasks",
        lambda: client.sell.marketing.get_report_tasks(limit="1", raw_response=True),
        lambda p, _r: {"count": count_key(p, "reportTasks"), "total": get(p, "total")},
    )
    runner.run(
        "sell.negotiation.find_eligible_items",
        lambda: client.sell.negotiation.find_eligible_items(
            x_ebay_c_marketplace_id=marketplace,
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "eligibleItems"), "total": get(p, "total")},
    )
    runner.run(
        "sell.recommendation.find_listing_recommendations",
        lambda: client.sell.recommendation.find_listing_recommendations(
            x_ebay_c_marketplace_id=marketplace,
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "listingRecommendations"), "total": get(p, "total")},
    )

    run_metadata_smokes(client, runner, marketplace, language)
    run_commerce_smokes(client, runner, marketplace)
    run_post_order_smokes(client, runner)
    run_store_and_restricted_smokes(client, runner, marketplace)
    run_buy_smokes(client, runner, marketplace, language)


def run_metadata_smokes(
    client: EbayClient,
    runner: SmokeRunner,
    marketplace: str,
    language: str,
) -> None:
    metadata = client.sell.metadata
    for label, call, keys in [
        (
            "sell.metadata.get_currencies",
            lambda: metadata.get_currencies(marketplace, raw_response=True),
            ("currencies",),
        ),
        (
            "sell.metadata.get_shipping_services",
            lambda: metadata.get_shipping_services(
                marketplace,
                accept_language=language,
                raw_response=True,
            ),
            ("shippingServices",),
        ),
        (
            "sell.metadata.get_shipping_carriers",
            lambda: metadata.get_shipping_carriers(
                marketplace,
                accept_language=language,
                raw_response=True,
            ),
            ("shippingCarriers",),
        ),
        (
            "sell.metadata.get_shipping_locations",
            lambda: metadata.get_shipping_locations(
                marketplace,
                accept_language=language,
                raw_response=True,
            ),
            ("shippingLocations",),
        ),
        (
            "sell.metadata.get_handling_times",
            lambda: metadata.get_handling_times(
                marketplace,
                accept_language=language,
                raw_response=True,
            ),
            ("handlingTimes",),
        ),
        (
            "sell.metadata.get_item_condition_policies",
            lambda: metadata.get_item_condition_policies(
                marketplace,
                accept_language=language,
                raw_response=True,
            ),
            ("itemConditionPolicies",),
        ),
        (
            "sell.metadata.get_category_policies",
            lambda: metadata.get_category_policies(
                marketplace,
                accept_language=language,
                raw_response=True,
            ),
            ("categoryPolicies",),
        ),
        (
            "sell.metadata.get_listing_structure_policies",
            lambda: metadata.get_listing_structure_policies(
                marketplace,
                accept_language=language,
                raw_response=True,
            ),
            ("listingStructurePolicies",),
        ),
        (
            "sell.metadata.get_return_policies",
            lambda: metadata.get_return_policies(
                marketplace,
                accept_language=language,
                raw_response=True,
            ),
            ("returnPolicies",),
        ),
        (
            "sell.metadata.get_shipping_policies",
            lambda: metadata.get_shipping_policies(
                marketplace,
                accept_language=language,
                raw_response=True,
            ),
            ("shippingPolicies",),
        ),
        (
            "sell.metadata.get_site_visibility_policies",
            lambda: metadata.get_site_visibility_policies(
                marketplace,
                accept_language=language,
                raw_response=True,
            ),
            ("siteVisibilityPolicies",),
        ),
        (
            "sell.metadata.get_regulatory_policies",
            lambda: metadata.get_regulatory_policies(
                marketplace,
                accept_language=language,
                raw_response=True,
            ),
            ("regulatoryPolicies",),
        ),
    ]:
        runner.run(label, call, lambda p, _r, ks=keys: {"count": count_key(p, *ks)})

    runner.run(
        "sell.metadata.get_hazardous_materials_labels",
        lambda: metadata.get_hazardous_materials_labels(marketplace, raw_response=True),
        lambda p, _r: {
            "signalWords": count_key(p, "signalWords"),
            "statements": count_key(p, "statements"),
            "pictograms": count_key(p, "pictograms"),
        },
    )
    runner.run(
        "sell.metadata.get_product_safety_labels",
        lambda: metadata.get_product_safety_labels(marketplace, raw_response=True),
        lambda p, _r: {
            "statements": count_key(p, "statements"),
            "pictograms": count_key(p, "pictograms"),
        },
    )
    runner.run(
        "sell.metadata.get_sales_tax_jurisdictions",
        lambda: metadata.get_sales_tax_jurisdictions("DE", raw_response=True),
        lambda p, _r: {"count": count_key(p, "salesTaxJurisdictions")},
    )


def run_commerce_smokes(client: EbayClient, runner: SmokeRunner, marketplace: str) -> None:
    runner.run(
        "commerce.catalog.search",
        lambda: client.commerce.catalog.search(
            q="radio",
            limit="1",
            x_ebay_c_marketplace_id=marketplace,
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "products"), "total": get(p, "total")},
    )
    runner.run(
        "commerce.charity.get_charity_orgs",
        lambda: client.commerce.charity.get_charity_orgs(
            x_ebay_c_marketplace_id=marketplace,
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "charityOrgs"), "total": get(p, "total")},
    )
    runner.run(
        "commerce.notification.get_topics",
        lambda: client.commerce.notification.get_topics(limit="10", raw_response=True),
        lambda p, _r: {"count": count_key(p, "topics"), "total": get(p, "total")},
    )
    runner.run(
        "commerce.notification.get_config",
        lambda: client.commerce.notification.get_config(raw_response=True),
        lambda p, _r: {
            "hasConfig": isinstance(p, dict),
            "keys": sorted(p)[:5] if isinstance(p, dict) else None,
        },
    )
    runner.run(
        "commerce.notification.get_destinations",
        lambda: client.commerce.notification.get_destinations(raw_response=True),
        lambda p, _r: {"count": count_key(p, "destinations")},
    )
    runner.run(
        "commerce.notification.get_subscriptions",
        lambda: client.commerce.notification.get_subscriptions(raw_response=True),
        lambda p, _r: {"count": count_key(p, "subscriptions")},
    )
    runner.run(
        "commerce.message.get_conversations.from_members",
        lambda: client.commerce.message.get_conversations(
            conversation_type="FROM_MEMBERS",
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "conversations"), "total": get(p, "total")},
    )
    runner.run(
        "commerce.message.get_conversations.from_ebay",
        lambda: client.commerce.message.get_conversations(
            conversation_type="FROM_EBAY",
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "conversations"), "total": get(p, "total")},
    )
    runner.run(
        "commerce.vero.get_vero_reason_codes",
        lambda: client.commerce.vero.get_vero_reason_codes(
            x_ebay_c_marketplace_id=marketplace,
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "reasonCodes", "veroReasonCodes")},
    )


def run_post_order_smokes(client: EbayClient, runner: SmokeRunner) -> None:
    runner.run(
        "post_order.case.search",
        lambda: client.post_order.case.search(limit=1, raw_response=True),
        lambda p, _r: {"count": count_key(p, "members", "cases"), "total": get(p, "total")},
    )
    runner.run(
        "post_order.inquiry.search",
        lambda: client.post_order.inquiry.search(limit=1, raw_response=True),
        lambda p, _r: {"count": count_key(p, "members", "inquiries"), "total": get(p, "total")},
    )
    runner.run(
        "post_order.return.search",
        lambda: client.post_order.return_.search(limit=1, raw_response=True),
        lambda p, _r: {"count": count_key(p, "members", "returns"), "total": get(p, "total")},
    )
    runner.run(
        "post_order.return.get_return_preferences",
        lambda: client.post_order.return_.get_return_preferences(raw_response=True),
        lambda p, _r: scrub(p),
    )
    runner.run(
        "post_order.cancellation.search",
        lambda: client.post_order.cancellation.search(raw_response=True),
        lambda _p, r: {"bytes": len(r.content)},
    )


def run_store_and_restricted_smokes(
    client: EbayClient,
    runner: SmokeRunner,
    marketplace: str,
) -> None:
    runner.run(
        "sell.stores.get_store",
        lambda: client.sell.stores.get_store(raw_response=True),
        lambda p, _r: {"name": get(p, "name") or get(get(p, "store", {}), "name")},
    )
    runner.run(
        "sell.stores.get_store_categories",
        lambda: client.sell.stores.get_store_categories(raw_response=True),
        lambda p, _r: {"count": count_key(p, "customCategories", "storeCategories")},
    )
    runner.run(
        "sell.stores.get_store_tasks",
        lambda: client.sell.stores.get_store_tasks(raw_response=True),
        lambda p, _r: {"count": count_key(p, "tasks")},
    )
    runner.run(
        "sell.leads.get_all_classified_leads",
        lambda: client.sell.leads.get_all_classified_leads(raw_response=True),
        lambda p, _r: {"count": count_key(p, "classifiedLeads")},
    )
    runner.run(
        "sell.edelivery_international_shipping.get_services",
        lambda: client.sell.edelivery_international_shipping.get_services(
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "services")},
    )
    runner.run(
        "sell.edelivery_international_shipping.get_agents",
        lambda: client.sell.edelivery_international_shipping.get_agents(raw_response=True),
        lambda p, _r: {"count": count_key(p, "agents")},
    )
    runner.run(
        "sell.analytics.find_seller_standards_profiles",
        lambda: client.sell.analytics.find_seller_standards_profiles(raw_response=True),
        lambda p, _r: {"count": count_key(p, "standardsProfiles"), "total": get(p, "total")},
    )
    runner.run(
        "sell.compliance.get_listing_violations_summary",
        lambda: client.sell.compliance.get_listing_violations_summary(
            x_ebay_c_marketplace_id=marketplace,
            raw_response=True,
        ),
        lambda p, _r: {"summaryKeys": sorted(p)[:6] if isinstance(p, dict) else None},
    )
    runner.run(
        "sell.compliance.get_listing_violations",
        lambda: client.sell.compliance.get_listing_violations(
            x_ebay_c_marketplace_id=marketplace,
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "complianceViolations"), "total": get(p, "total")},
    )


def run_buy_smokes(
    client: EbayClient,
    runner: SmokeRunner,
    marketplace: str,
    language: str,
) -> None:
    browse = runner.run(
        "buy.browse.search",
        lambda: client.buy.browse.search(
            q="radio",
            limit="1",
            x_ebay_c_marketplace_id=marketplace,
            accept_language=language,
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "itemSummaries"), "total": get(p, "total")},
    )
    item_id = get(pick_first(browse, "itemSummaries"), "itemId")
    if item_id:
        runner.run(
            "buy.browse.get_item",
            lambda: client.buy.browse.get_item(
                item_id,
                x_ebay_c_marketplace_id=marketplace,
                accept_language=language,
                raw_response=True,
            ),
            lambda p, _r: {
                "itemId": get(p, "itemId"),
                "price": get(get(p, "price", {}), "currency"),
            },
        )
        runner.run(
            "buy.marketing.get_similar_items",
            lambda: client.buy.marketing.get_similar_items(
                item_id=item_id,
                x_ebay_c_marketplace_id=marketplace,
                accept_language=language,
                max_results="1",
                raw_response=True,
            ),
            lambda p, _r: {"count": count_key(p, "itemSummaries", "items")},
        )
    runner.run(
        "buy.deal.get_events",
        lambda: client.buy.deal.get_events(
            x_ebay_c_marketplace_id=marketplace,
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "events"), "total": get(p, "total")},
    )
    runner.run(
        "buy.deal.get_deal_items",
        lambda: client.buy.deal.get_deal_items(
            x_ebay_c_marketplace_id=marketplace,
            limit="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "dealItems"), "total": get(p, "total")},
    )
    runner.run(
        "buy.marketing.get_most_watched_items",
        lambda: client.buy.marketing.get_most_watched_items(
            category_id="293",
            x_ebay_c_marketplace_id=marketplace,
            accept_language=language,
            max_results="1",
            raw_response=True,
        ),
        lambda p, _r: {"count": count_key(p, "itemSummaries", "items")},
    )


def run_inventory_probe(client: EbayClient, runner: SmokeRunner, args: argparse.Namespace) -> None:
    source_item = getattr(args, "_source_inventory_item", None)
    if not isinstance(source_item, dict):
        print("Progress: skipped inventory write probe; no source inventory item", flush=True)
        return

    allowed = {
        "availability",
        "condition",
        "conditionDescription",
        "conditionDescriptors",
        "packageWeightAndSize",
        "product",
    }
    body = {key: copy.deepcopy(value) for key, value in source_item.items() if key in allowed}
    product = body.setdefault("product", {})
    if isinstance(product, dict):
        product["title"] = TEST_TITLE
        description = str(product.get("description") or "")
        product["description"] = ("DYDYDDYDYDYD ABABABABABA\n" + description)[:4000]

    print(f"Progress: creating patterned inventory item sku={TEST_SKU}", flush=True)
    runner.run(
        "sell.inventory.create_or_replace_inventory_item.pattern",
        lambda: client.sell.inventory.create_or_replace_inventory_item(
            TEST_SKU,
            body=cast(Any, body),
            content_language=args.language,
            content_type="application/json",
            raw_response=True,
        ),
        lambda _p, _r: {"sku": TEST_SKU, "bodyKeys": sorted(body)},
    )
    runner.run(
        "sell.inventory.get_inventory_item.pattern",
        lambda: client.sell.inventory.get_inventory_item(TEST_SKU, raw_response=True),
        lambda p, _r: {"sku": get(p, "sku"), "title": get(get(p, "product", {}), "title")},
    )
    if args.keep_inventory_probe:
        print(f"Progress: kept patterned inventory item sku={TEST_SKU}", flush=True)
        return
    runner.run(
        "sell.inventory.delete_inventory_item.pattern",
        lambda: client.sell.inventory.delete_inventory_item(TEST_SKU, raw_response=True),
        lambda _p, r: {"sku": TEST_SKU, "deleted": r.status_code in (200, 202, 204)},
    )


def run_media_probe(client: EbayClient, runner: SmokeRunner, args: argparse.Namespace) -> None:
    if args.image.exists():

        def upload_image() -> httpx.Response:
            content_type = mimetypes.guess_type(args.image.name)[0] or "image/jpeg"
            with args.image.open("rb") as file:
                return client.commerce.media.create_image_from_file(
                    files={"image": (args.image.name, file, content_type)},
                    raw_response=True,
                )

        image_payload = runner.run(
            "commerce.media.create_image_from_file",
            upload_image,
            lambda p, r: {
                "imageId": get(p, "imageId") or image_id_from_location(r),
                "location": r.headers.get("Location") or r.headers.get("location"),
                "imageUrl": get(p, "imageUrl"),
            },
        )
        image_id = get(image_payload, "imageId")
        if not image_id:
            image_id = image_id_from_location_from_rows(runner.rows)
        if image_id:
            runner.run(
                "commerce.media.get_image",
                lambda: client.commerce.media.get_image(image_id, raw_response=True),
                lambda p, _r: {
                    "imageId": get(p, "imageId"),
                    "status": get(p, "status"),
                    "imageUrl": bool(get(p, "imageUrl")),
                },
            )
    else:
        print(f"Progress: image missing at {args.image}", flush=True)

    if args.video.exists():
        size = args.video.stat().st_size
        body = {
            "title": "ABABABABABA",
            "size": size,
            "classification": ["ITEM"],
            "description": "DYDYDDYDYDYD",
        }
        runner.run(
            "commerce.media.create_video",
            lambda: client.commerce.media.create_video(
                content_type="application/json",
                body=cast(Any, body),
                raw_response=True,
            ),
            lambda _p, r: {
                "location": r.headers.get("Location") or r.headers.get("location"),
                "bytes": len(r.content),
            },
        )
        location = None
        for row in reversed(runner.rows):
            is_create_video = row["label"] == "commerce.media.create_video"
            if is_create_video and isinstance(row.get("detail"), dict):
                location = row["detail"].get("location")
                break
        video_id = video_id_from_location(location)
        if video_id:
            print(f"Progress: uploading video id={video_id} bytes={size}", flush=True)
            runner.run(
                "commerce.media.upload_video",
                lambda: client.commerce.media.upload_video(
                    video_id,
                    body=args.video.read_bytes(),
                    raw_response=True,
                ),
                lambda _p, r: {
                    "videoId": video_id,
                    "uploaded": r.status_code in (200, 201, 202, 204),
                },
            )
            runner.run(
                "commerce.media.get_video",
                lambda: client.commerce.media.get_video(video_id, raw_response=True),
                lambda p, _r: {
                    "videoId": get(p, "videoId"),
                    "status": get(p, "status"),
                    "statusMessage": get(p, "statusMessage"),
                    "expirationDate": get(p, "expirationDate"),
                },
            )
    else:
        print(f"Progress: video missing at {args.video}", flush=True)


def parse_response(response: httpx.Response) -> Any:
    if not response.content:
        return None
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            return orjson.loads(response.content)
        except Exception:
            return {"unparsed_json_bytes": len(response.content)}
    text = response.text.strip()
    return {"content_type": content_type, "text": text[:500], "bytes": len(response.content)}


def compact_error(payload: Any) -> str:
    if isinstance(payload, dict):
        errors = payload.get("errors") or payload.get("error") or payload.get("warnings")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                bits = [
                    str(first.get(key))
                    for key in ("errorId", "domain", "category", "message")
                    if first.get(key)
                ]
                return " | ".join(bits)[:500]
        for key in ("message", "error_description", "longMessage"):
            if payload.get(key):
                return str(payload[key])[:500]
    if isinstance(payload, str):
        return payload[:500]
    return ""


def scrub(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "..."
    if isinstance(value, dict):
        return {
            key: "<redacted>" if key in SENSITIVE_KEYS else scrub(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub(item, depth + 1) for item in value[:20]]
    return value


def count_key(payload: Any, *keys: str) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, int):
            return value
    return None


def pick_first(payload: Any, *keys: str) -> Any:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list) and value:
                return value[0]
    return None


def get(payload: Any, key: str, default: Any = None) -> Any:
    return payload.get(key, default) if isinstance(payload, dict) else default


def image_id_from_location(response: httpx.Response) -> str | None:
    location = response.headers.get("Location") or response.headers.get("location")
    return video_id_from_location(location)


def image_id_from_location_from_rows(rows: list[dict[str, Any]]) -> str | None:
    for row in reversed(rows):
        if row["label"] != "commerce.media.create_image_from_file":
            continue
        detail = row.get("detail")
        if isinstance(detail, dict):
            return video_id_from_location(detail.get("location"))
    return None


def video_id_from_location(location: Any) -> str | None:
    if not isinstance(location, str) or not location:
        return None
    match = re.search(r"/(?:video|image)/([^/?#]+)", location)
    if match:
        return match.group(1)
    return location.rstrip("/").split("/")[-1]


if __name__ == "__main__":
    main()
