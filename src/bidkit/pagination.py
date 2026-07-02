"""Auto-paging helpers for eBay list endpoints.

eBay paginates list responses with a `limit`/`offset` window and usually also returns a
fully-formed `next` URL. These helpers drive a generated list method across pages and yield the
individual items, so callers can write::

    for payout in paginate(client.sell.finances.get_payouts, limit="50"):
        ...

The collection field is auto-detected (the single list-valued field that is not eBay paging
metadata); pass ``items_field`` to override when a response carries several arrays.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel

# Arrays that are not the paginated collection (eBay returns these alongside results).
_METADATA_LIST_FIELDS = frozenset(
    {"warnings", "errors", "refinement", "refinements", "auto_corrections"}
)


def _collection_field(model: BaseModel, items_field: str | None) -> str:
    if items_field is not None:
        return items_field
    candidates = [
        name
        for name in type(model).model_fields
        if name not in _METADATA_LIST_FIELDS and isinstance(getattr(model, name, None), list)
    ]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(
        f"Could not infer the collection field on {type(model).__name__} "
        f"(candidates: {candidates or 'none'}); pass items_field=..."
    )


def _paging_source(model: BaseModel) -> BaseModel:
    """The object carrying the paging fields.

    Most eBay responses expose ``next``/``offset``/``limit``/``total`` at the top level, but
    some (e.g. the Feedback API) nest them under a ``pagination`` object.
    """
    if getattr(model, "next", None) or getattr(model, "offset", None) is not None:
        return model
    nested = getattr(model, "pagination", None)
    return nested if isinstance(nested, BaseModel) else model


def _next_page_kwargs(source: BaseModel) -> dict[str, str] | None:
    """Paging kwargs for the next page, or ``None`` when the last page was reached."""
    next_url = getattr(source, "next", None)
    if isinstance(next_url, str) and next_url:
        query = parse_qs(urlsplit(next_url).query)
        update = {key: query[key][0] for key in ("offset", "limit") if key in query}
        return update or None

    total, limit, offset = (getattr(source, name, None) for name in ("total", "limit", "offset"))
    if total is None or limit is None or offset is None:
        return None
    try:
        total, limit, offset = int(total), int(limit), int(offset)
    except (TypeError, ValueError):
        return None
    if limit <= 0 or offset + limit >= total:
        return None
    return {"offset": str(offset + limit)}


def _advance(model: object, kwargs: dict[str, Any], seen_offsets: set[str]) -> bool:
    """Mutate ``kwargs`` toward the next page. Returns False to stop."""
    if not isinstance(model, BaseModel):
        return False
    update = _next_page_kwargs(_paging_source(model))
    if not update:
        return False
    offset = update.get("offset")
    if offset is not None:
        if offset in seen_offsets:  # guard against a server that never advances
            return False
        seen_offsets.add(offset)
    kwargs.update(update)
    return True


def paginate(
    method: Callable[..., Any],
    *args: Any,
    items_field: str | None = None,
    max_items: int | None = None,
    **kwargs: Any,
) -> Iterator[Any]:
    """Yield items across all pages of a generated list ``method``.

    ``args``/``kwargs`` are forwarded to ``method`` (path params positionally, query params as
    keywords); ``offset``/``limit`` are managed automatically as pages advance.
    """
    yielded = 0
    seen_offsets: set[str] = set()
    while True:
        model = method(*args, **kwargs)
        if model is None:  # endpoints return an empty body when nothing matches
            return
        items = getattr(model, _collection_field(model, items_field), None) or []
        for item in items:
            yield item
            yielded += 1
            if max_items is not None and yielded >= max_items:
                return
        if not items or not _advance(model, kwargs, seen_offsets):
            return


async def paginate_async(
    method: Callable[..., Awaitable[Any]],
    *args: Any,
    items_field: str | None = None,
    max_items: int | None = None,
    **kwargs: Any,
) -> AsyncIterator[Any]:
    """Async counterpart of :func:`paginate` for ``AsyncEbayClient`` methods."""
    yielded = 0
    seen_offsets: set[str] = set()
    while True:
        model = await method(*args, **kwargs)
        if model is None:  # endpoints return an empty body when nothing matches
            return
        items = getattr(model, _collection_field(model, items_field), None) or []
        for item in items:
            yield item
            yielded += 1
            if max_items is not None and yielded >= max_items:
                return
        if not items or not _advance(model, kwargs, seen_offsets):
            return
