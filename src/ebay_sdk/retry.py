"""Retry policy for transient eBay responses.

eBay throttles with ``429 Too Many Requests`` (often carrying ``Retry-After``) and
occasionally returns transient ``5xx`` errors. This module centralises the decision of
*whether* to retry and *how long* to wait, so the sync and async transports share one policy.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from .config import EbayConfig

# Methods safe to replay because eBay treats them as idempotent. ``POST`` is excluded except
# for 429s, where the request was rejected before processing and is therefore safe to resend.
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})


def should_retry_status(method: str, status_code: int, config: EbayConfig) -> bool:
    if status_code not in config.retry_statuses:
        return False
    if status_code == 429:
        return True
    return method.upper() in _IDEMPOTENT_METHODS


def should_retry_exception(method: str) -> bool:
    return method.upper() in _IDEMPOTENT_METHODS


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    now = datetime.now(when.tzinfo or UTC)
    return max(0.0, (when - now).total_seconds())


def status_retry_delay(
    attempt: int, response: httpx.Response, method: str, config: EbayConfig
) -> float | None:
    """Delay before retrying a response, or ``None`` if it should not be retried."""
    if attempt >= config.max_retries or not should_retry_status(
        method, response.status_code, config
    ):
        return None
    return compute_delay(attempt, response, config)


def exception_retry_delay(attempt: int, method: str, config: EbayConfig) -> float | None:
    """Delay before retrying after a connection error, or ``None`` if it should not be retried."""
    if attempt >= config.max_retries or not should_retry_exception(method):
        return None
    return compute_delay(attempt, None, config)


def compute_delay(attempt: int, response: httpx.Response | None, config: EbayConfig) -> float:
    """Seconds to wait before the next attempt (0-indexed ``attempt``).

    Honors ``Retry-After`` when present; otherwise uses exponential backoff with full jitter,
    both capped at ``retry_max_backoff``.
    """
    if response is not None and config.respect_retry_after:
        retry_after = _retry_after_seconds(response)
        if retry_after is not None:
            return min(retry_after, config.retry_max_backoff)
    ceiling = min(config.retry_backoff * (2**attempt), config.retry_max_backoff)
    return random.uniform(0, ceiling)
