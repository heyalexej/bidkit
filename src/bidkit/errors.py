from __future__ import annotations

from typing import Any

import httpx
import orjson


class EbaySDKError(Exception):
    """Base exception for all SDK-level failures."""


class EbayConfigError(EbaySDKError):
    """Raised when SDK configuration is incomplete or invalid."""


class EbayTransportError(EbaySDKError):
    """Raised for network-level failures before eBay returns a response."""


class EbayAuthError(EbaySDKError):
    """Raised when OAuth token acquisition or refresh fails."""


class EbayAPIError(EbaySDKError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        response: httpx.Response | None = None,
        payload: Any = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response
        self.payload = payload
        self.request_id = request_id

    @classmethod
    def from_response(cls, response: httpx.Response) -> EbayAPIError:
        payload: Any
        try:
            payload = orjson.loads(response.content)
        except orjson.JSONDecodeError:
            payload = response.text

        message = response.reason_phrase or f"eBay API returned HTTP {response.status_code}"
        if isinstance(payload, dict):
            errors = payload.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict):
                    message = first.get("message") or first.get("longMessage") or message
            elif payload.get("error_description"):
                message = str(payload["error_description"])
            elif payload.get("message"):
                message = str(payload["message"])

        return cls(
            message,
            status_code=response.status_code,
            response=response,
            payload=payload,
            request_id=response.headers.get("x-ebay-c-request-id")
            or response.headers.get("x-ebay-request-id"),
        )
