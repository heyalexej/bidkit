---
description: >-
  Iterate all pages of eBay API list endpoints in Python with bidkit's paginate and
  paginate_async helpers — next-URL following, offset arithmetic, and item caps.
---

# Paginate eBay API results

eBay paginates list responses with a `limit`/`offset` window and usually also returns a
fully-formed `next` URL. `paginate` (sync) and `paginate_async` drive any generated list
method across pages and yield the individual items:

```python
from bidkit import paginate

for payout in paginate(client.sell.finances.get_payouts, limit=50):
    print(payout.payout_id)
```

```python
from bidkit import paginate_async

async for item in paginate_async(client.sell.inventory.get_inventory_items, limit=100):
    ...
```

## How it works

- Positional path params and query keywords are forwarded to the method; `offset`/`limit`
  are managed as pages advance.
- The `next` URL is followed when present; otherwise `offset + limit < total` arithmetic
  decides. Responses that nest paging metadata in a `pagination` object (e.g. the Feedback
  API) are handled too.
- A guard stops iteration if a server ever repeats an offset, so a misbehaving endpoint
  cannot loop forever.

## Options

- `max_items=N` — stop after N items regardless of page count.
- `items_field="..."` — name the collection field explicitly when a response carries more
  than one array (otherwise it is auto-detected as the single non-metadata list field).
