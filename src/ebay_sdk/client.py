from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import TYPE_CHECKING, Any

import httpx

from .auth import EbayAuth, TokenCache
from .config import EbayConfig
from .transport import AsyncEbayTransport, EbayTransport

if TYPE_CHECKING:
    from .generated.resources import (
        AsyncBuyNamespace,
        AsyncCommerceNamespace,
        AsyncDeveloperNamespace,
        AsyncPostOrderNamespace,
        AsyncSellNamespace,
        BuyNamespace,
        CommerceNamespace,
        DeveloperNamespace,
        PostOrderNamespace,
        SellNamespace,
    )


class EbayClient:
    buy: BuyNamespace
    commerce: CommerceNamespace
    developer: DeveloperNamespace
    post_order: PostOrderNamespace
    sell: SellNamespace

    def __init__(
        self,
        config: EbayConfig | Mapping[str, Any] | None = None,
        *,
        http_client: httpx.Client | None = None,
        token_cache: TokenCache | None = None,
    ) -> None:
        self.config = (
            config if isinstance(config, EbayConfig) else EbayConfig.model_validate(config or {})
        )
        self.http = http_client or httpx.Client(timeout=self.config.timeout)
        self.auth = EbayAuth(self.config, token_cache)
        self._transport = EbayTransport(self.config, self.auth, self.http)

        from .generated.resources import install_sync_namespaces

        install_sync_namespaces(self)

    @classmethod
    def from_env(cls) -> EbayClient:
        return cls(EbayConfig.from_env())

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> EbayClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def request(self, **kwargs: Any) -> Any:
        return self._transport.request(**kwargs)

    def stream(self, **kwargs: Any) -> AbstractContextManager[httpx.Response]:
        return self._transport.stream(**kwargs)


class AsyncEbayClient:
    buy: AsyncBuyNamespace
    commerce: AsyncCommerceNamespace
    developer: AsyncDeveloperNamespace
    post_order: AsyncPostOrderNamespace
    sell: AsyncSellNamespace

    def __init__(
        self,
        config: EbayConfig | Mapping[str, Any] | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
        token_cache: TokenCache | None = None,
    ) -> None:
        self.config = (
            config if isinstance(config, EbayConfig) else EbayConfig.model_validate(config or {})
        )
        self.http = http_client or httpx.AsyncClient(timeout=self.config.timeout)
        self.auth = EbayAuth(self.config, token_cache)
        self._transport = AsyncEbayTransport(self.config, self.auth, self.http)

        from .generated.resources import install_async_namespaces

        install_async_namespaces(self)

    @classmethod
    def from_env(cls) -> AsyncEbayClient:
        return cls(EbayConfig.from_env())

    async def close(self) -> None:
        await self.http.aclose()

    async def __aenter__(self) -> AsyncEbayClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def request(self, **kwargs: Any) -> Any:
        return await self._transport.request(**kwargs)

    def stream(self, **kwargs: Any) -> AbstractAsyncContextManager[httpx.Response]:
        return self._transport.stream(**kwargs)
