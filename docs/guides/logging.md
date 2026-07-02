---
description: >-
  Observe eBay API traffic from Python: bidkit's structured logging for requests, retries,
  and token refreshes, plus OpenTelemetry via httpx instrumentation.
---

# Logging & observability

bidkit is silent by default and logs through the standard library under the `bidkit`
namespace, so it composes with plain `logging`, structlog capture, JSON formatters, and
OpenTelemetry handlers alike. Opt in per subsystem:

```python
import logging

logging.basicConfig(level=logging.INFO)
logging.getLogger("bidkit").setLevel(logging.DEBUG)   # or just "bidkit.retry"
```

```
DEBUG:bidkit.transport:getPayouts GET https://apiz.ebay.com/sell/finances/v1/payout -> 200 (312 ms)
INFO:bidkit.auth:refreshed user token for refresh:1a2b3c4d… (expires in 7200 s)
WARNING:bidkit.retry:getOrders attempt 1/3: HTTP 429, retrying in 1.8 s (Retry-After)
```

## Level policy

| Logger | Level | Event |
|---|---|---|
| `bidkit.transport` | DEBUG | every completed request: operation, method, URL, status, elapsed ms |
| `bidkit.auth` | INFO | token minted/refreshed (grant kind + hashed identity only) |
| `bidkit.retry` | WARNING | each retry: attempt, status or exception, delay, Retry-After vs backoff |

Failures raise exceptions instead of being logged twice.

## Structured fields

Every record carries `extra` fields (`operation`, `method`, `url`, `status`, `elapsed_ms`,
`attempt`, `max_attempts`, `delay_s`, `reason`, `grant`, `expires_in`) so JSON/structured
formatters get real fields without parsing messages.

**Secrets are never logged** — no tokens, no `Authorization` headers, no request bodies;
user grants are identified only by a hashed refresh-token prefix.

## Wire-level detail and tracing

For socket-level detail, enable httpx's own loggers (`httpx`, `httpcore`) at DEBUG. For
distributed tracing, the OpenTelemetry httpx instrumentation works out of the box, since
bidkit rides on httpx.
