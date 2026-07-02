---
description: >-
  Verify eBay push notification signatures in Python and answer the endpoint-validation
  challenge — including the mandatory marketplace account deletion notifications.
---

# Verify eBay push notifications

Production eBay applications must expose a notification endpoint — at minimum for the
mandatory **marketplace account deletion** topic. Two things happen on that endpoint, and
bidkit handles the cryptography for both.

## 1. Endpoint validation (challenge)

When you register the endpoint, eBay sends `GET ?challenge_code=...`. Respond `200` with
`Content-Type: application/json` and the hash eBay expects:

```python
from bidkit import challenge_response

body = challenge_response(challenge_code, VERIFICATION_TOKEN, "https://your.app/ebay/hook")
# -> {"challengeResponse": "<sha256 hex of challengeCode + verificationToken + endpoint>"}
```

## 2. Notification delivery (signature verification)

Each `POST` carries an `x-ebay-signature` header. Verify it against the **raw body bytes**
before parsing anything:

```python
from bidkit import EbayClient, EbayConfig, NotificationVerifier

client = EbayClient(EbayConfig(app_id="...", cert_id="..."))   # app credentials suffice
verifier = NotificationVerifier(client)                        # keys cached ~1 hour

if verifier.verify(raw_body_bytes, request.headers["x-ebay-signature"]):
    ...   # handle the event; respond 204
else:
    ...   # respond 412 Precondition Failed; eBay retries
```

`AsyncNotificationVerifier` is the drop-in for async frameworks (FastAPI, aiohttp, …).

### FastAPI sketch

```python
@app.get("/ebay/hook")
def challenge(challenge_code: str):
    return challenge_response(challenge_code, TOKEN, ENDPOINT)

@app.post("/ebay/hook")
async def notification(request: Request):
    body = await request.body()
    if await verifier.verify(body, request.headers.get("x-ebay-signature", "")):
        return Response(status_code=204)
    return Response(status_code=412)
```

### Semantics

- `verify` returns `False` for a bad or malformed signature → respond **412** (eBay
  retries and alerts you if the endpoint stays down).
- It raises only on operational failures (public-key fetch, unsupported key type) →
  respond **500**.
- Signatures are ECDSA (P-256) over the raw payload; the public key comes from the
  Notification API's `getPublicKey` and is cached for an hour, per eBay's guidance. The
  scheme matches eBay's official event-notification SDKs.
