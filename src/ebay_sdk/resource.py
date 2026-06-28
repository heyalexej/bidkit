from __future__ import annotations

import importlib
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Any, NotRequired, TypedDict

import httpx


class _LazyModule:
    """Import a generated model module on first attribute access.

    Resource bodies reference models as ``<service>_models.SomeModel``. Binding that alias to
    this proxy defers the (expensive) model import until a method of that service is actually
    called, so constructing a client no longer imports all 40+ model modules up front.
    """

    __slots__ = ("_name", "_module")

    def __init__(self, name: str) -> None:
        self._name = name
        self._module: Any = None

    def __getattr__(self, attr: str) -> Any:
        module = self._module
        if module is None:
            module = importlib.import_module(self._name)
            self._module = module
        return getattr(module, attr)


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
