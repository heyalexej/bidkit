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

## Server quirk: the Feedback API breaks hand-rolled offset loops

`commerce.feedback.get_feedback` does not behave like the rest of the platform, and the
two stop conditions people normally reach for both fail on it. Use `paginate` — it follows
`pagination.next` and is unaffected — or reproduce the behaviour below carefully.

**Short pages appear mid-stream.** A page can come back with far fewer entries than
`limit` while `pagination.next` is still set and `pagination.total` is orders of magnitude
higher. Observed on a real account with `limit=50`:

| offset | entries | total | next |
| --- | --- | --- | --- |
| 0 | 5 | 8301 | `…&offset=50` |
| 50 | 12 | 8301 | `…&offset=100` |
| 100 | 10 | 8301 | `…&offset=150` |

So `len(entries) < limit` does **not** mean end of data. A loop that stops there returns 5
of 8301 entries and reports success.

**Past-the-end offsets repeat the last page instead of returning nothing.** For an account
with `pagination.total = 100`, every offset from 100 upwards — including 500 — still
returns a full page of 50 entries, identical to the previous one, with `pagination.next`
correctly set to `None`. So "stop when a page comes back empty" never fires and the loop
runs forever.

**Pages can overlap.** The same `feedback_id` may appear on more than one page; one 3000-item
run contained 2957 distinct ids. Deduplicate by `feedback_id` when exact counts matter.

The reliable signals are `pagination.next` (becomes `None` at the end) and
`pagination.total`. `paginate` uses both:

```python
from bidkit import paginate

entries = list(paginate(
    client.commerce.feedback.get_feedback,
    user_id="some_user",
    feedback_type="FEEDBACK_RECEIVED",
    limit=50,
))
```

Note that the built-in repeated-offset guard does not help here: a hand-rolled loop
increments the offset itself, so each request carries a fresh offset and the guard never
sees a repeat — only the server's response body is stuck.

## Options

- `max_items=N` — stop after N items regardless of page count.
- `items_field="..."` — name the collection field explicitly when a response carries more
  than one array (otherwise it is auto-detected as the single non-metadata list field).
