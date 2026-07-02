---
description: >-
  Configure the bidkit eBay API client in Python: environment variables, config files,
  marketplaces, and scoped per-call overrides with with_options().
---

# Configuration

Everything is driven by `EbayConfig` — construct it directly, from the environment, or
from a config file.

## From the environment

```python
client = EbayClient.from_env()
```

reads `EBAY_APP_ID`, `EBAY_CERT_ID`, `EBAY_DEV_ID`, `EBAY_RU_NAME`, `EBAY_REFRESH_TOKEN`,
`EBAY_ACCESS_TOKEN`, `EBAY_SCOPES` (space-separated), `EBAY_MARKETPLACE_ID`,
`EBAY_ACCEPT_LANGUAGE`, `EBAY_CONTENT_LANGUAGE`, `EBAY_SANDBOX`, `EBAY_BASE_URL`, and the
signing variables (`EBAY_SIGNING_KEY_FILE`, or `EBAY_SIGNING_JWE` +
`EBAY_SIGNING_PRIVATE_KEY`).

## From a config file

`EbayConfig.from_file()` loads an ebay-cli style `config.json`
(default `~/.config/ebay-cli/config.json`):

```python
client = EbayClient(EbayConfig.from_file())
```

Credentials live under a `credentials` object with the usual aliases
(`app_id`/`client_id`, `cert_id`/`client_secret`, `ru_name`/`redirect_uri`,
`granted_scopes`/`scopes`); top-level `environment` and `marketplace_default` map to
`sandbox` and `marketplace_id`. A `signing-key.json` next to the config is picked up
automatically.

## Marketplace and languages

`marketplace_id` (default `EBAY_US`) is sent as `X-EBAY-C-MARKETPLACE-ID` on every request;
methods that accept it as a parameter can override it per call. `accept_language` /
`content_language` default to `en-US`.

## Scoped overrides: with_options

Any config field can be overridden for a subset of calls without touching the base client:

```python
fast = client.with_options(timeout=5.0, max_retries=0)
fast.sell.inventory.get_offers(sku="ABC-1")

de = client.with_options(marketplace_id="EBAY_DE")
```

The scoped client shares the HTTP connection pool and token cache — no new connections, no
re-auth — and closing it never closes the shared pool.

## Injecting your own httpx client

Pass `http_client=` for custom proxies, transports, or event hooks. bidkit never closes a
client it didn't create:

```python
client = EbayClient(config, http_client=httpx.Client(proxy="http://proxy:3128"))
```
