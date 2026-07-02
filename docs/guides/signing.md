---
description: >-
  eBay digital signatures in Python: sign Finances API and refund calls with RFC 9421-style
  HTTP message signatures (Ed25519/RSA) automatically with bidkit.
---

# Digital signatures (Finances API)

The Finances API and several refund operations reject requests unless they carry an
RFC 9421-style HTTP message signature (`x-ebay-signature-key` + `Signature` headers) —
an EU/UK payments-regulation requirement. Provide signing material and bidkit signs
**exactly the operations eBay requires**:

```python
from bidkit import EbayClient, EbayConfig, EbaySigningConfig

client = EbayClient(EbayConfig(
    refresh_token="...",
    signing=EbaySigningConfig(jwe="<jwe>", private_key="<pem>"),  # or .from_key_file(path)
))
client.sell.finances.get_payouts(limit=3)   # signed; 200 instead of 403
client.buy.browse.search(q="...")           # NOT signed — eBay doesn't expect it here
```

## What gets signed

- Every **Finances API** method.
- **Fulfillment `issueRefund`** and the **Post-Order issue-refund** operations
  (`issue_case_refund`, `issue_inquiry_refund`, `issue_return_refund`).

Everything else is left untouched. If eBay expands its signed list before the SDK updates,
`EbaySigningConfig(..., sign_all=True)` signs every request as an escape hatch.

## Keys

The `jwe` and private key come from eBay's Key Management API
(`client.developer.key_management`). Ed25519 (eBay's default) and RSA keys are supported;
the private key may be a full PEM block or the bare base64 PKCS#8 body. Signing material
can also come from the environment (`EBAY_SIGNING_KEY_FILE`, or `EBAY_SIGNING_JWE` +
`EBAY_SIGNING_PRIVATE_KEY`) or from an ebay-cli style `signing-key.json` next to your
config file.
