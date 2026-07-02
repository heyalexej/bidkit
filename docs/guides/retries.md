---
description: >-
  How bidkit retries eBay API rate limits (429) and transient errors, and how to check
  your remaining eBay call quota from Python.
---

# Retries & rate limits

## Automatic retries

`429 Too Many Requests` and transient `5xx` (500/502/503/504) responses are retried with
exponential backoff + full jitter, honoring `Retry-After` when eBay sends one. Retries are
method-aware: idempotent methods (`GET`/`HEAD`/`OPTIONS`/`PUT`/`DELETE`) are replayed on
both 429 and 5xx; non-idempotent `POST` only on 429 (the request was rejected before
processing). Connection errors retry for idempotent methods.

```python
EbayConfig(
    max_retries=2,                       # 0 disables retries
    retry_statuses=(429, 500, 502, 503, 504),
    retry_backoff=0.5,                   # base seconds; delay = backoff * 2**attempt
    retry_max_backoff=60.0,
    respect_retry_after=True,
)
```

Scoped override without touching the base client:

```python
client.with_options(max_retries=0, timeout=5.0).sell.fulfillment.get_orders(limit=5)
```

Retries are visible at `WARNING` on the `bidkit.retry` logger — see
[Logging](logging.md).

## Checking your remaining quota

eBay does not send quota headers on responses. Remaining call quota lives behind two
Developer Analytics lookups that need **different token types**:

```python
# Application quota — requires an application token (client credentials, base scope)
app = client.with_options(refresh_token=None, scopes=("https://api.ebay.com/oauth/api_scope",))
for rl in app.developer.analytics.get_rate_limits().rate_limits or []:
    ...

# Per-user quota — requires the user token
for rl in client.developer.analytics.get_user_rate_limits().rate_limits or []:
    ...
```

!!! warning "Filter quirks"
    The `api_context`/`api_name` server-side filters are case-sensitive and unreliable, and
    eBay's payload mixes casings (`"Sell"`, `"commerce"`, `"TradingAPI"`). Fetch unfiltered
    and filter client-side.
