from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Any, NotRequired, TypedDict

import httpx


class Service(TypedDict):
    """Static descriptor of a generated eBay API, attached to each resource class."""

    key: str
    title: str
    version: str
    base_path: str
    subdomain: str
    auth_scheme: NotRequired[str]


class BaseResource:
    service: Service

    def __init__(self, client: Any) -> None:
        self._client = client

    def _request(
        self,
        operation_id: str,
        method: str,
        path: str,
        *,
        path_params: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str | None] | None = None,
        body: Any = None,
        files: Mapping[str, Any] | None = None,
        response_model: Any = None,
        raw_response: bool = False,
    ) -> Any:
        return self._client.request(
            service=self.service,
            operation_id=operation_id,
            method=method,
            path=path,
            path_params=path_params,
            params=params,
            headers=headers,
            body=body,
            files=files,
            response_model=response_model,
            raw_response=raw_response,
        )

    def _stream(
        self,
        operation_id: str,
        method: str,
        path: str,
        *,
        path_params: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str | None] | None = None,
        body: Any = None,
        files: Mapping[str, Any] | None = None,
    ) -> AbstractContextManager[httpx.Response]:
        return self._client.stream(
            service=self.service,
            operation_id=operation_id,
            method=method,
            path=path,
            path_params=path_params,
            params=params,
            headers=headers,
            body=body,
            files=files,
        )


class AsyncBaseResource:
    service: Mapping[str, Any]

    def __init__(self, client: Any) -> None:
        self._client = client

    async def _request(
        self,
        operation_id: str,
        method: str,
        path: str,
        *,
        path_params: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str | None] | None = None,
        body: Any = None,
        files: Mapping[str, Any] | None = None,
        response_model: Any = None,
        raw_response: bool = False,
    ) -> Any:
        return await self._client.request(
            service=self.service,
            operation_id=operation_id,
            method=method,
            path=path,
            path_params=path_params,
            params=params,
            headers=headers,
            body=body,
            files=files,
            response_model=response_model,
            raw_response=raw_response,
        )

    def _stream(
        self,
        operation_id: str,
        method: str,
        path: str,
        *,
        path_params: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str | None] | None = None,
        body: Any = None,
        files: Mapping[str, Any] | None = None,
    ) -> AbstractAsyncContextManager[httpx.Response]:
        return self._client.stream(
            service=self.service,
            operation_id=operation_id,
            method=method,
            path=path,
            path_params=path_params,
            params=params,
            headers=headers,
            body=body,
            files=files,
        )
