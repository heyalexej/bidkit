---
description: >-
  bidkit vs ebaysdk — how the modern typed Python SDK for eBay's REST APIs relates to the
  legacy XML-era ebaysdk package, and which one you need.
---

# bidkit vs ebaysdk

Python developers searching for an eBay SDK usually find
[`ebaysdk`](https://pypi.org/project/ebaysdk/) first. The two packages cover **different
eras of eBay's platform** and are complementary, not competing:

| | **bidkit** | **ebaysdk** |
|---|---|---|
| APIs | eBay **REST** APIs (Sell, Buy, Commerce, Developer, Post-Order) | Legacy **XML** APIs (Trading, Finding, Shopping, Merchandising) |
| Status | Actively maintained | Community package, unmaintained (last release 2020) |
| Official? | No (unofficial, MIT) | No — widely assumed official because eBay's developer site historically linked it |
| Auth | OAuth 2.0 (app + user tokens, auto-refresh) | Token/credential files |
| Types | Full Pydantic v2 models, `py.typed`, typed operations | Dict/XML responses |
| Async | Yes (`AsyncEbayClient`) | No |
| Signatures | eBay digital signatures (Finances API) built in | — |
| Python | 3.11+ | 2.7/3.x era |

**Use bidkit** for everything eBay ships as REST — which is all current Sell/Buy/Commerce
functionality, including Inventory, Fulfillment, Finances, Marketing, and Browse.

**Use `ebaysdk` alongside** only if you need a legacy XML call (e.g. a Trading API feature
without a REST equivalent). There is no official, maintained Python SDK for eBay's REST
APIs — that gap is exactly what bidkit fills.
