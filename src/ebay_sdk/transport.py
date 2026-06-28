from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Any
from urllib.parse import quote

import httpx
import orjson
from pydantic import BaseModel, TypeAdapter

from .auth import EbayAuth
from .config import EbayConfig
from .errors import EbayAPIError, EbayTransportError
from .retry import compute_delay, should_retry_exception, should_retry_status
from .signing import MessageSigner


def _url(
    config: EbayConfig,
    service: Mapping[str, Any],
    path: str,
    path_params: Mapping[str, Any] | None,
) -> str:
    rendered_path = path
    for key, value in (path_params or {}).items():
        rendered_path = rendered_path.replace("{" + key + "}", quote(str(value), safe=""))
    root = config.api_root(str(service.get("subdomain") or "api"))
    return f"{root}{service['base_path']}{rendered_path}"


def _headers(
    config: EbayConfig,
    service: Mapping[str, Any],
    extra_headers: Mapping[str, str | None] | None,
) -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": config.marketplace_id,
    }
    if config.accept_language:
        headers["Accept-Language"] = config.accept_language
    if config.content_language:
        headers["Content-Language"] = config.content_language

    if service.get("default_content_type"):
        headers["Content-Type"] = str(service["default_content_type"])

    for key, value in (extra_headers or {}).items():
        if value is not None:
            headers[key] = str(value)
    return headers


def _auth_scheme(service: Mapping[str, Any]) -> str:
    return str(service.get("auth_scheme") or "Bearer")


def _body_kwargs(*, body: Any, files: Mapping[str, Any] | None) -> dict[str, Any]:
    if files is not None:
        return {"files": files}
    if body is None:
        return {}
    if isinstance(body, bytes | bytearray | memoryview):
        return {"content": body}
    if isinstance(body, BaseModel):
        payload = body.model_dump(by_alias=True, exclude_none=True)
    else:
        payload = body
    return {"content": orjson.dumps(payload)}


def _handle_response(response: httpx.Response, response_model: Any, raw_response: bool) -> Any:
    if raw_response:
        return response
    if response.status_code >= 400:
        raise EbayAPIError.from_response(response)
    if response.status_code == 204 or not response.content:
        return None

    content_type = response.headers.get("content-type", "")
    if "json" not in content_type:
        if response_model is str:
            return response.text
        return response.content
    payload = orjson.loads(response.content)
    if response_model is None:
        return payload
    return TypeAdapter(response_model).validate_python(payload)


def _compact(values: Mapping[str, Any] | None) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, value in (values or {}).items():
        if value is None:
            continue
        compacted[key] = (
            ",".join(str(item) for item in value)
            if isinstance(value, list | tuple)
            else value
        )
    return compacted


def _build_signer(config: EbayConfig) -> MessageSigner | None:
    if config.signing is None:
        return None
    return MessageSigner(
        jwe=config.signing.jwe,
        private_key_pem=config.signing.private_key_value,
        digest=config.signing.digest,
    )


def _sign_request(signer: MessageSigner | None, request: httpx.Request) -> None:
    if signer is None:
        return
    signature_headers = signer.headers(
        method=request.method,
        authority=request.url.host,
        path=request.url.path,
        body=request.content or None,
        created=int(time.time()),
    )
    for key, value in signature_headers.items():
        request.headers[key] = value


class EbayTransport:
    def __init__(self, config: EbayConfig, auth: EbayAuth, client: httpx.Client) -> None:
        self.config = config
        self.auth = auth
        self.client = client
        self._signer = _build_signer(config)

    def request(
        self,
        *,
        service: Mapping[str, Any],
        operation_id: str,
        method: str,
        path: str,
        path_params: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str | None] | None = None,
        body: Any = None,
        files: Mapping[str, Any] | None = None,
        response_model: Any = None,
        raw_response: bool = False,
    ) -> Any:
        url = _url(self.config, service, path, path_params)
        compacted = _compact(params)
        request_headers = _headers(self.config, service, headers)
        request_headers.update(self.auth.authorization_header(
            self.client,
            scheme=_auth_scheme(service),
        ))
        body_kwargs = _body_kwargs(body=body, files=files)

        response: httpx.Response | None = None
        for attempt in range(self.config.max_retries + 1):
            request = self.client.build_request(
                method, url, params=compacted, headers=request_headers, **body_kwargs
            )
            _sign_request(self._signer, request)
            try:
                response = self.client.send(request)
            except httpx.TransportError as exc:
                if attempt < self.config.max_retries and should_retry_exception(method):
                    time.sleep(compute_delay(attempt, None, self.config))
                    continue
                raise EbayTransportError(f"{operation_id} transport failure: {exc}") from exc
            except httpx.HTTPError as exc:
                raise EbayTransportError(f"{operation_id} transport failure: {exc}") from exc

            if attempt < self.config.max_retries and should_retry_status(
                method, response.status_code, self.config
            ):
                delay = compute_delay(attempt, response, self.config)
                response.close()
                time.sleep(delay)
                continue
            break

        assert response is not None
        return _handle_response(response, response_model, raw_response)

    @contextmanager
    def stream(
        self,
        *,
        service: Mapping[str, Any],
        operation_id: str,
        method: str,
        path: str,
        path_params: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str | None] | None = None,
        body: Any = None,
        files: Mapping[str, Any] | None = None,
    ) -> Iterator[httpx.Response]:
        url = _url(self.config, service, path, path_params)
        compacted = _compact(params)
        request_headers = _headers(self.config, service, headers)
        request_headers.update(self.auth.authorization_header(
            self.client,
            scheme=_auth_scheme(service),
        ))
        body_kwargs = _body_kwargs(body=body, files=files)

        response: httpx.Response | None = None
        for attempt in range(self.config.max_retries + 1):
            request = self.client.build_request(
                method, url, params=compacted, headers=request_headers, **body_kwargs
            )
            _sign_request(self._signer, request)
            try:
                response = self.client.send(request, stream=True)
            except httpx.TransportError as exc:
                if attempt < self.config.max_retries and should_retry_exception(method):
                    time.sleep(compute_delay(attempt, None, self.config))
                    continue
                raise EbayTransportError(f"{operation_id} stream failure: {exc}") from exc
            except httpx.HTTPError as exc:
                raise EbayTransportError(f"{operation_id} stream failure: {exc}") from exc

            if attempt < self.config.max_retries and should_retry_status(
                method, response.status_code, self.config
            ):
                response.read()
                delay = compute_delay(attempt, response, self.config)
                response.close()
                time.sleep(delay)
                continue
            break

        assert response is not None
        try:
            if response.status_code >= 400:
                response.read()
                raise EbayAPIError.from_response(response)
            yield response
        finally:
            response.close()


class AsyncEbayTransport:
    def __init__(self, config: EbayConfig, auth: EbayAuth, client: httpx.AsyncClient) -> None:
        self.config = config
        self.auth = auth
        self.client = client
        self._signer = _build_signer(config)

    async def request(
        self,
        *,
        service: Mapping[str, Any],
        operation_id: str,
        method: str,
        path: str,
        path_params: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str | None] | None = None,
        body: Any = None,
        files: Mapping[str, Any] | None = None,
        response_model: Any = None,
        raw_response: bool = False,
    ) -> Any:
        url = _url(self.config, service, path, path_params)
        compacted = _compact(params)
        request_headers = _headers(self.config, service, headers)
        request_headers.update(await self.auth.async_authorization_header(
            self.client,
            scheme=_auth_scheme(service),
        ))
        body_kwargs = _body_kwargs(body=body, files=files)

        response: httpx.Response | None = None
        for attempt in range(self.config.max_retries + 1):
            request = self.client.build_request(
                method, url, params=compacted, headers=request_headers, **body_kwargs
            )
            _sign_request(self._signer, request)
            try:
                response = await self.client.send(request)
            except httpx.TransportError as exc:
                if attempt < self.config.max_retries and should_retry_exception(method):
                    await asyncio.sleep(compute_delay(attempt, None, self.config))
                    continue
                raise EbayTransportError(f"{operation_id} transport failure: {exc}") from exc
            except httpx.HTTPError as exc:
                raise EbayTransportError(f"{operation_id} transport failure: {exc}") from exc

            if attempt < self.config.max_retries and should_retry_status(
                method, response.status_code, self.config
            ):
                delay = compute_delay(attempt, response, self.config)
                await response.aclose()
                await asyncio.sleep(delay)
                continue
            break

        assert response is not None
        return _handle_response(response, response_model, raw_response)

    @asynccontextmanager
    async def stream(
        self,
        *,
        service: Mapping[str, Any],
        operation_id: str,
        method: str,
        path: str,
        path_params: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str | None] | None = None,
        body: Any = None,
        files: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[httpx.Response]:
        url = _url(self.config, service, path, path_params)
        compacted = _compact(params)
        request_headers = _headers(self.config, service, headers)
        request_headers.update(await self.auth.async_authorization_header(
            self.client,
            scheme=_auth_scheme(service),
        ))
        body_kwargs = _body_kwargs(body=body, files=files)

        response: httpx.Response | None = None
        for attempt in range(self.config.max_retries + 1):
            request = self.client.build_request(
                method, url, params=compacted, headers=request_headers, **body_kwargs
            )
            _sign_request(self._signer, request)
            try:
                response = await self.client.send(request, stream=True)
            except httpx.TransportError as exc:
                if attempt < self.config.max_retries and should_retry_exception(method):
                    await asyncio.sleep(compute_delay(attempt, None, self.config))
                    continue
                raise EbayTransportError(f"{operation_id} stream failure: {exc}") from exc
            except httpx.HTTPError as exc:
                raise EbayTransportError(f"{operation_id} stream failure: {exc}") from exc

            if attempt < self.config.max_retries and should_retry_status(
                method, response.status_code, self.config
            ):
                await response.aread()
                delay = compute_delay(attempt, response, self.config)
                await response.aclose()
                await asyncio.sleep(delay)
                continue
            break

        assert response is not None
        try:
            if response.status_code >= 400:
                await response.aread()
                raise EbayAPIError.from_response(response)
            yield response
        finally:
            await response.aclose()
