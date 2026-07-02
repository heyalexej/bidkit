---
description: >-
  How to authenticate with the eBay API in Python: application tokens, user refresh
  tokens, the OAuth authorization-code flow, and persistent token caching with bidkit.
---

# eBay OAuth in Python

eBay's REST APIs use OAuth 2.0 with two grant types, and bidkit handles both
automatically once configured.

## Application tokens (client credentials)

For APIs that act on behalf of your application (Browse, Taxonomy, getting notification
public keys, …), `app_id` + `cert_id` are all you need:

```python
from bidkit import EbayClient, EbayConfig

client = EbayClient(EbayConfig(app_id="...", cert_id="..."))
client.buy.browse.search(q="fountain pen", limit=10)
```

bidkit mints the token on first use, caches it, and refreshes before expiry. Concurrent
callers hitting a stale token trigger exactly one refresh (per-key locking), and cache keys
are tenant-safe — a shared cache never returns another credential's token.

## User tokens (refresh token)

To act on behalf of a seller (Inventory, Fulfillment, Finances, …), add the seller's
`refresh_token`:

```python
client = EbayClient(EbayConfig(app_id="...", cert_id="...", refresh_token="v^1...."))
```

## Getting a refresh token (authorization-code flow)

The consent flow is a one-time, three-step exchange:

```python
client = EbayClient(EbayConfig(app_id="...", cert_id="...", ru_name="...", scopes=(...,)))

# 1. Send the user to the consent URL.
print(client.authorization_url(state="..."))

# 2. eBay redirects to your RuName's accepted URL with ?code=<...>; capture that code.
# 3. Exchange it — this also authenticates the client immediately.
tokens = client.exchange_code(code)
print(tokens.refresh_token)   # persist; pass back as EbayConfig(refresh_token=...)
```

Only the redirect capture (step 2) needs the HTTPS "accepted URL" registered for your
RuName — the exchange itself is a plain backend call. `exchange_code` stores the refresh
token on the client's config, so the same client is immediately authorized.

!!! tip
    The repository ships `scripts/oauth_login.py`, which runs the whole flow interactively
    (opens the browser, captures the redirect, optionally persists the token).

## Token caching

Tokens are cached in memory by default, so each new process mints a fresh one. For CLIs and
scripts, persist them across runs:

```python
from bidkit import EbayClient, FileTokenCache

client = EbayClient(config, token_cache=FileTokenCache())
```

`FileTokenCache` stores tokens in a `0600` JSON file (default
`~/.cache/bidkit/tokens.json`) with atomic writes and expired-entry pruning. Any object
implementing the two-method `TokenCache` protocol (`get`/`set`) works — e.g. Redis for
multi-host deployments. See the [auth reference](../reference/auth.md).

## Sandbox

`EbayConfig(sandbox=True)` routes everything to `*.sandbox.ebay.com`. Sandbox needs its own
`...-SBX-...` keyset — a production App ID fails with `invalid_client`.
