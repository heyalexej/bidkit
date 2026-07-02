---
description: >-
  bidkit is a modern, typed Python SDK for the eBay REST APIs — sync and async clients
  generated from eBay's OpenAPI contracts, with OAuth, retries, and digital signatures.
---

# bidkit

A modern, typed **Python SDK for the eBay REST APIs** — sync and async, generated from
eBay's OpenAPI contracts.

!!! note "Unofficial"
    This project is not affiliated with or endorsed by eBay Inc. "eBay" is a trademark of
    eBay Inc. See [NOTICE](https://github.com/heyalexej/bidkit/blob/main/NOTICE).

## Installation

```bash
uv add bidkit          # or: pip install bidkit
```

Requires Python 3.11+.

## Quickstart

```python
from bidkit import EbayClient, EbayConfig

client = EbayClient(EbayConfig(app_id="...", cert_id="..."))  # or EbayClient.from_env()
results = client.buy.browse.search(q="vintage radio", limit=5)
for item in results.item_summaries or []:
    print(item.title, item.price.value if item.price else "?")
```

Every one of the **455 operations across 41 eBay APIs** is a typed method with Pydantic
request/response models — see [Supported eBay APIs](reference/apis.md).

## Why bidkit

- **Typed end to end** — Pydantic v2 models generated from eBay's own contracts; unknown
  fields and new enum values never break validation; `raw_response=True` narrows to
  `httpx.Response` in your type checker.
- **Sync and async** on httpx, with orjson serialization.
- **OAuth built in** — client-credentials and user tokens, stampede-proof refresh caching,
  a persistent [`FileTokenCache`](guides/authentication.md#token-caching), and the
  authorization-code flow as three lines of code.
- **Automatic retries** with `Retry-After` support and full-jitter backoff —
  [tunable per call](guides/retries.md).
- **eBay digital signatures** (RFC 9421-style) applied exactly where eBay requires them —
  [Finances API and refund operations](guides/signing.md).
- **Push notification verification** for webhook endpoints, including the mandatory
  marketplace-account-deletion topic — [guide](guides/notifications.md).
- **Fast imports** — lazy-loaded model modules keep client construction at tens of
  milliseconds.

## Scope

bidkit covers eBay's **REST APIs** (Sell, Buy, Commerce, Developer, Post-Order). The legacy
XML APIs are out of scope by design — see [bidkit vs ebaysdk](comparison.md).
