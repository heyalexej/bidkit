"""Comprehensive read-only smoke of the local bidkit SDK against eBay PRODUCTION (EBAY_DE).

Covers the read-only (GET) surface, chaining real IDs discovered at runtime
(sku -> offer, order, campaign, inventory location, ...) and exercising the
auto-paging helpers against high-volume account data (inventory, orders,
transactions).

Creds come from the ebay-cli skill config (~/.config/ebay-cli/config.json).
Every op is GET / read-only. Run from the repo root:

    uv run --extra dev scripts/smoke_de.py
"""

from __future__ import annotations

import contextlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pydantic import BaseModel, ValidationError  # noqa: E402

from bidkit import (  # noqa: E402
    EbayAPIError,
    EbayClient,
    EbayConfig,
    EbaySigningConfig,
    paginate,
)

MKT = "EBAY_DE"
COUNTRY = "DE"
cr = json.loads((Path.home() / ".config/ebay-cli/config.json").read_text())["credentials"]

GREEN, RED, YEL, BLU, DIM, RST = (
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[34m",
    "\033[2m",
    "\033[0m",
)

# Load digital-signature material if present so the Finances API works (otherwise 403).
_signing_key = Path.home() / ".config/ebay-cli/signing-key.json"
signing = EbaySigningConfig.from_key_file(_signing_key) if _signing_key.exists() else None

client = EbayClient(
    EbayConfig(
        app_id=cr["app_id"],
        cert_id=cr["cert_id"],
        refresh_token=cr["refresh_token"],
        marketplace_id=MKT,
        scopes=tuple(cr["granted_scopes"]),
        signing=signing,
    )
)

_passes = _apierr = _modelerr = _fail = 0


def summarize(val: object) -> str:
    if isinstance(val, BaseModel):
        d = val.model_dump(exclude_none=True)
        extra = ""
        for k, v in d.items():
            if isinstance(v, list):
                extra = f"  [{k}={len(v)}]"
                break
        return f"{type(val).__name__} {list(d)[:6]}{extra}"
    if isinstance(val, (bytes, bytearray)):
        return f"<{len(val)} bytes>"
    return repr(val)[:160]


def run(label: str, fn: Callable[[], Any]) -> Any:
    """Call fn(); record + print outcome. Returns the value on success else None."""
    global _passes, _apierr, _modelerr, _fail
    try:
        val = fn()
        _passes += 1
        print(f"{GREEN}  PASS {RST}{label}\n        {DIM}{summarize(val)}{RST}")
        return val
    except ValidationError as e:
        _modelerr += 1
        first = e.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        print(
            f"{RED}  MODEL{RST}{label}\n        {DIM}{len(e.errors())} validation err(s); "
            f"first: {loc}: {first['msg']}{RST}"
        )
    except EbayAPIError as e:
        _apierr += 1
        print(f"{YEL}  API{e.status_code}{RST} {label}\n        {DIM}{str(e)[:160]}{RST}")
    except Exception as e:  # noqa: BLE001
        _fail += 1
        print(f"{RED}  FAIL {RST}{label}: {type(e).__name__}: {str(e)[:160]}")
    return None


def paged(
    label: str, method: Callable[..., Any], *args: Any, cap: int = 500, **kwargs: Any
) -> None:
    """Auto-page a list endpoint and report how many items came back across pages."""
    global _passes, _apierr, _modelerr, _fail
    try:
        count = 0
        first: Any = None
        for item in paginate(method, *args, max_items=cap, **kwargs):
            if first is None:
                first = item
            count += 1
        _passes += 1
        kind = type(first).__name__ if first is not None else "empty"
        note = f"  (capped at {cap})" if count >= cap else ""
        print(f"{GREEN}  PAGE {RST}{label}\n        {DIM}{count} x {kind}{note}{RST}")
    except ValidationError as e:
        _modelerr += 1
        first_err = e.errors()[0]
        loc = ".".join(str(p) for p in first_err["loc"])
        print(
            f"{RED}  MODEL{RST}{label}\n        {DIM}{len(e.errors())} validation err(s); "
            f"first: {loc}: {first_err['msg']}{RST}"
        )
    except EbayAPIError as e:
        _apierr += 1
        print(f"{YEL}  API{e.status_code}{RST} {label}\n        {DIM}{str(e)[:160]}{RST}")
    except Exception as e:  # noqa: BLE001
        _fail += 1
        print(f"{RED}  FAIL {RST}{label}: {type(e).__name__}: {str(e)[:160]}")


def section(name: str) -> None:
    print(f"\n{BLU}== {name} =={RST}")


s = client.sell
co = client.commerce
dev = client.developer

# ---- discover IDs we can chain from ----
section("discovery (for id chaining)")
items = run(
    "sell.inventory.get_inventory_items(limit=10)",
    lambda: s.inventory.get_inventory_items(limit="10"),
)
sku = None
if items and getattr(items, "inventory_items", None):
    sku = items.inventory_items[0].sku
    print(f"        {DIM}-> sku={sku}{RST}")
orders = run(
    "sell.fulfillment.get_orders(limit=5)",
    lambda: s.fulfillment.get_orders(limit="5"),
)
order_id = orders.orders[0].order_id if orders and getattr(orders, "orders", None) else None
if order_id:
    print(f"        {DIM}-> order_id={order_id}{RST}")
username = None
with contextlib.suppress(Exception):
    username = co.identity.get_user().username
if username:
    print(f"        {DIM}-> username={username}{RST}")

# ---- pagination (auto-paging across real account data) ----
section("pagination (auto-paging)")
paged("inventory.get_inventory_items", s.inventory.get_inventory_items, limit="20")
paged("fulfillment.get_orders", s.fulfillment.get_orders, limit="20")
paged("finances.get_transactions (signed)", s.finances.get_transactions, limit="20")
paged(
    "finances.get_transactions fees (NON_SALE_CHARGE, signed)",
    s.finances.get_transactions,
    limit="20",
    filter="transactionType:{NON_SALE_CHARGE}",
)
paged("finances.get_payouts (signed)", s.finances.get_payouts, limit="20")
paged(
    "message.get_conversations",
    co.message.get_conversations,
    conversation_type="ALL",
    limit="20",
)
if username:
    paged(
        "feedback.get_feedback (nested pagination)",
        co.feedback.get_feedback,
        feedback_type="FEEDBACK_RECEIVED",
        user_id=str(username),
        limit="20",
    )
paged("marketing.get_campaigns", s.marketing.get_campaigns, limit="20")

# ---- sell.inventory (rest of surface) ----
section("sell.inventory")
if sku:
    run(f"get_inventory_item({sku})", lambda: s.inventory.get_inventory_item(str(sku)))
    run(
        f"get_product_compatibility({sku})",
        lambda: s.inventory.get_product_compatibility(str(sku)),
    )
    offers = run(f"get_offers(sku={sku})", lambda: s.inventory.get_offers(sku=str(sku)))
    if offers and getattr(offers, "offers", None):
        oid = offers.offers[0].offer_id
        run(f"get_offer({oid})", lambda: s.inventory.get_offer(str(oid)))
locs = run("get_inventory_locations", lambda: s.inventory.get_inventory_locations(limit="5"))
if locs and getattr(locs, "locations", None):
    key = locs.locations[0].merchant_location_key
    run(f"get_inventory_location({key})", lambda: s.inventory.get_inventory_location(str(key)))

# ---- sell.account (rest of surface) ----
section("sell.account")
run("get_opted_in_programs", lambda: s.account.get_opted_in_programs())
run("get_rate_tables", lambda: s.account.get_rate_tables(country_code=COUNTRY))
run(
    "get_custom_policies",
    lambda: s.account.get_custom_policies(
        x_ebay_c_marketplace_id=MKT, policy_types="PRODUCT_COMPLIANCE,TAKE_BACK"
    ),
)
run("get_subscription", lambda: s.account.get_subscription())
run("get_kyc", lambda: s.account.get_kyc())
run(
    "get_advertising_eligibility",
    lambda: s.account.get_advertising_eligibility(x_ebay_c_marketplace_id=MKT),
)
run("get_sales_taxes", lambda: s.account.get_sales_taxes(country_code=COUNTRY))
run("get_privileges", lambda: s.account.get_privileges())
run("account_v2.get_payout_settings", lambda: s.account_v2.get_payout_settings())

# ---- sell.fulfillment (rest) ----
section("sell.fulfillment")
if order_id:
    run(f"get_order({order_id})", lambda: s.fulfillment.get_order(str(order_id)))
    run(
        f"get_shipping_fulfillments({order_id})",
        lambda: s.fulfillment.get_shipping_fulfillments(str(order_id)),
    )
run("get_payment_dispute_summaries", lambda: s.fulfillment.get_payment_dispute_summaries())

# ---- sell.compliance ----
section("sell.compliance")
run(
    "get_listing_violations_summary",
    lambda: s.compliance.get_listing_violations_summary(x_ebay_c_marketplace_id=MKT),
)
run(
    "get_listing_violations",
    lambda: s.compliance.get_listing_violations(
        x_ebay_c_marketplace_id=MKT, compliance_type="PRODUCT_ADOPTION"
    ),
)

# ---- sell.analytics (rest) ----
section("sell.analytics")
run(
    "get_traffic_report",
    lambda: s.analytics.get_traffic_report(
        dimension="DAY",
        metric="LISTING_IMPRESSION_TOTAL,TRANSACTION",
        filter="marketplace_ids:{EBAY_DE},date_range:[20260601..20260627]",
    ),
)
run(
    "get_customer_service_metric(ITEM_NOT_AS_DESCRIBED/CURRENT)",
    lambda: s.analytics.get_customer_service_metric(
        "ITEM_NOT_AS_DESCRIBED", "CURRENT", evaluation_marketplace_id=MKT
    ),
)
run(
    "get_seller_standards_profile(CURRENT/PROGRAM_DE)",
    lambda: s.analytics.get_seller_standards_profile("CURRENT", "PROGRAM_DE"),
)

# ---- sell.feed ----
section("sell.feed")
run(
    "get_inventory_tasks(LMS_ACTIVE_INVENTORY_REPORT)",
    lambda: s.feed.get_inventory_tasks(
        feed_type="LMS_ACTIVE_INVENTORY_REPORT", look_back_days="7"
    ),
)
run(
    "get_order_tasks(LMS_ORDER_REPORT)",
    lambda: s.feed.get_order_tasks(feed_type="LMS_ORDER_REPORT", look_back_days="7"),
)
run(
    "get_tasks(LMS_ORDER_REPORT)",
    lambda: s.feed.get_tasks(feed_type="LMS_ORDER_REPORT", look_back_days="7"),
)
run(
    "get_schedules(feed_type=LMS_ORDER_REPORT)",
    lambda: s.feed.get_schedules(feed_type="LMS_ORDER_REPORT"),
)
run(
    "get_customer_service_metric_tasks(CUSTOMER_SERVICE_METRICS_REPORT)",
    lambda: s.feed.get_customer_service_metric_tasks(
        feed_type="CUSTOMER_SERVICE_METRICS_REPORT", look_back_days="7"
    ),
)

# ---- sell.marketing ----
section("sell.marketing")
camps = run("get_campaigns", lambda: s.marketing.get_campaigns(limit="5"))
cid = camps.campaigns[0].campaign_id if camps and getattr(camps, "campaigns", None) else None
if cid:
    print(f"        {DIM}-> campaign_id={cid}{RST}")
    run(f"get_campaign({cid})", lambda: s.marketing.get_campaign(str(cid)))
    run(f"get_ads({cid})", lambda: s.marketing.get_ads(str(cid)))
    run(f"get_ad_groups({cid})", lambda: s.marketing.get_ad_groups(str(cid)))
    run(f"get_keywords({cid})", lambda: s.marketing.get_keywords(str(cid)))
run("get_promotions", lambda: s.marketing.get_promotions(marketplace_id=MKT, limit="5"))
run("get_email_campaigns", lambda: s.marketing.get_email_campaigns(limit="10", offset="0"))
run("get_report_metadata", lambda: s.marketing.get_report_metadata())

# ---- sell.metadata (marketplace-scoped) ----
section("sell.metadata")
run("get_item_condition_policies", lambda: s.metadata.get_item_condition_policies(MKT))
run("get_return_policies", lambda: s.metadata.get_return_policies(MKT))
run("get_listing_structure_policies", lambda: s.metadata.get_listing_structure_policies(MKT))
run("get_negotiated_price_policies", lambda: s.metadata.get_negotiated_price_policies(MKT))
run("get_hazardous_materials_labels", lambda: s.metadata.get_hazardous_materials_labels(MKT))
run(
    "get_extended_producer_responsibility_policies",
    lambda: s.metadata.get_extended_producer_responsibility_policies(MKT),
)
run(
    "get_automotive_parts_compatibility_policies",
    lambda: s.metadata.get_automotive_parts_compatibility_policies(MKT),
)

# ---- sell.finances (digitally signed; 403 without a signing key) ----
section(f"sell.finances (signing={'on' if signing else 'OFF -> expect 403'})")
run("get_seller_funds_summary", lambda: s.finances.get_seller_funds_summary())
run("get_payouts", lambda: s.finances.get_payouts(limit="5"))
run("get_payout_summary", lambda: s.finances.get_payout_summary())
run("get_transactions", lambda: s.finances.get_transactions(limit="5"))
run(
    "get_transaction_summary",
    lambda: s.finances.get_transaction_summary(filter="transactionStatus:{PAYOUT}"),
)

# ---- commerce.taxonomy (rest) ----
section("commerce.taxonomy")
tree = run(
    "get_default_category_tree_id",
    lambda: co.taxonomy.get_default_category_tree_id(marketplace_id=MKT),
)
tid = tree.category_tree_id if tree else None
if tid:
    run(f"get_category_tree({tid})", lambda: co.taxonomy.get_category_tree(str(tid)))
    run(
        f"get_category_suggestions({tid}, q=iphone)",
        lambda: co.taxonomy.get_category_suggestions(str(tid), q="iphone"),
    )

# ---- commerce.feedback ----
section("commerce.feedback")
if username:
    run(
        "get_feedback(FEEDBACK_RECEIVED)",
        lambda: co.feedback.get_feedback(
            feedback_type="FEEDBACK_RECEIVED", user_id=str(username), limit="5"
        ),
    )
run("get_items_awaiting_feedback", lambda: co.feedback.get_items_awaiting_feedback())

# ---- commerce.message ----
section("commerce.message")
run(
    "get_conversations(ALL)",
    lambda: co.message.get_conversations(conversation_type="ALL", limit="5"),
)

# ---- commerce.notification ----
section("commerce.notification")
run("get_config", lambda: co.notification.get_config())
run("get_topics", lambda: co.notification.get_topics(limit="10"))
run("get_subscriptions", lambda: co.notification.get_subscriptions(limit="10"))
run("get_destinations", lambda: co.notification.get_destinations(limit="10"))

# ---- developer ----
section("developer")
run("analytics.get_rate_limits", lambda: dev.analytics.get_rate_limits())
run("analytics.get_user_rate_limits", lambda: dev.analytics.get_user_rate_limits())
run("key_management.get_signing_keys", lambda: dev.key_management.get_signing_keys())

# ---- buy.* (seller token lacks buy scopes -> probe) ----
section("buy (probe — buy scopes not consented)")
run("browse.search(q=iphone)", lambda: client.buy.browse.search(q="iphone", limit="1"))

client.close()
total = _passes + _apierr + _modelerr + _fail
print(
    f"\n{BLU}== summary =={RST}  {GREEN}PASS={_passes}{RST}  "
    f"{YEL}API-err={_apierr}{RST}  {RED}MODEL-err={_modelerr}{RST}  "
    f"{RED}FAIL={_fail}{RST}  (total {total})"
)
