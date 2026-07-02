---
description: >-
  All 41 eBay REST APIs supported by bidkit — 455 typed Python operations across the Buy,
  Sell, Commerce, Developer, and Post-Order namespaces.
---

# Supported eBay APIs

All **41 eBay REST APIs** are generated and wired into the client across **5 namespaces**,
exposing **455 typed operations** on both `EbayClient` and `AsyncEbayClient`. Versions are
pinned to the OpenAPI contracts bundled in the repository.

Every operation is a typed method — your editor is the API reference:

```python
client.sell.finances.get_payouts(limit=10)        # -> Payouts (Pydantic model)
client.sell.finances.get_payouts(raw_response=True)  # -> httpx.Response
client.sell.logistics.stream_download_label_file(shipment_id, accept="application/pdf")
```

Each method carries the operation's documentation as its docstring, has a `raw_response`
overload, and binary downloads add a `stream_*` variant. Full endpoint semantics live in
[eBay's API documentation](https://developer.ebay.com/develop/apis).

## Buy — `client.buy` (29 ops)

| Accessor | API | Version | Ops | Maturity |
|---|---|---|---|---|
| `buy.browse` | Browse | `v1.20.4` | 7 | Stable |
| `buy.deal` | Deal | `v1.3.0` | 4 | Stable |
| `buy.feed` | Feed (Item Feed) | `v1_beta.35.3` | 4 | Beta |
| `buy.marketing` | Marketing | `1.1.0` | 3 | Stable |
| `buy.marketplace_insights` | Marketplace Insights | `v1_beta.2.0` | 1 | Beta |
| `buy.offer` | Offer | `v1_beta.0.1` | 2 | Beta |
| `buy.order` | Order | `v2.1.4` | 8 | Stable |

## Commerce — `client.commerce` (64 ops)

| Accessor | API | Version | Ops | Maturity |
|---|---|---|---|---|
| `commerce.catalog` | Catalog | `v1_beta.5.3` | 2 | Beta |
| `commerce.charity` | Charity | `v1.2.1` | 2 | Stable |
| `commerce.feedback` | Feedback | `v1.0.0` | 5 | Stable |
| `commerce.identity` | Identity | `v2.0.0` | 1 | Stable |
| `commerce.media` | Media | `v1_beta.5.1` | 13 | Beta |
| `commerce.message` | Message (M2M) | `1.0.0` | 5 | Stable |
| `commerce.notification` | Notification | `v1.6.7` | 21 | Stable |
| `commerce.taxonomy` | Taxonomy | `v1.1.1` | 9 | Stable |
| `commerce.translation` | Translation | `v1_beta.1.6` | 1 | Beta |
| `commerce.vero` | VeRO | `1.0.0` | 5 | Stable |

## Developer — `client.developer` (6 ops)

| Accessor | API | Version | Ops | Maturity |
|---|---|---|---|---|
| `developer.analytics` | Analytics | `v1_beta.0.1` | 2 | Beta |
| `developer.client_registration` | Client Registration | `v1.0.0` | 1 | Stable |
| `developer.key_management` | Key Management | `v1.0.0` | 3 | Stable |

## Post-Order — `client.post_order` (58 ops)

| Accessor | API | Version | Ops | Maturity |
|---|---|---|---|---|
| `post_order.cancellation` | Cancellation | `v2` * | 7 | Stable |
| `post_order.case` | Case Management | `v2` * | 7 | Stable |
| `post_order.inquiry` | Inquiry | `v2` * | 11 | Stable |
| `post_order.return_` | Return | `v2` * | 33 | Stable |

\* Post-Order specs carry `info.version` `0.1`, but the API is served at `/post-order/v2`.

## Sell — `client.sell` (298 ops)

| Accessor | API | Version | Ops | Maturity |
|---|---|---|---|---|
| `sell.account` | Account v1 | `v1.9.3` | 37 | Stable |
| `sell.account_v2` | Account v2 | `2.2.0` | 14 | Stable |
| `sell.analytics` | Analytics | `1.3.2` | 4 | Stable |
| `sell.compliance` | Compliance | `1.4.1` | 3 | Stable |
| `sell.edelivery_international_shipping` | eDelivery Intl Shipping (EDIS) | `1.1.0` | 27 | Stable |
| `sell.feed` | Feed | `v1.3.1` | 23 | Stable |
| `sell.finances` | Finances | `v1.19.0` | 11 | Stable † |
| `sell.fulfillment` | Fulfillment | `v1.20.6` | 15 | Stable |
| `sell.inventory` | Inventory | `1.18.5` | 36 | Stable |
| `sell.leads` | Classified Leads | `v1.0.0` | 2 | Stable |
| `sell.listing` | Listing | `v1_beta.2.1` | 1 | Beta |
| `sell.logistics` | Logistics | `v1_beta.0.0` | 6 | Beta |
| `sell.marketing` | Marketing | `v1.22.4` | 80 | Stable |
| `sell.metadata` | Metadata | `v1.13.0` | 28 | Stable |
| `sell.negotiation` | Negotiation | `v1.1.2` | 2 | Stable |
| `sell.recommendation` | Recommendation | `v1.1.0` | 1 | Stable |
| `sell.stores` | Store | `1` | 8 | Stable |

† Requires a digital signature — see [Digital signatures](../guides/signing.md).
