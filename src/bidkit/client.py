from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import TYPE_CHECKING, Any

import httpx

from .auth import EbayAuth, OAuthTokens, TokenCache
from .config import EbayConfig
from .errors import EbayConfigError
from .transport import AsyncEbayTransport, EbayTransport


def _authorization_url(
    config: EbayConfig,
    *,
    state: str | None,
    prompt: str | None,
    scopes: tuple[str, ...] | None,
) -> str:
    if not config.app_id or not config.ru_name:
        raise EbayConfigError("app_id and ru_name are required to build an authorization URL")
    return EbayAuth.authorization_url(
        app_id=config.app_id,
        ru_name=config.ru_name,
        scopes=scopes or config.scopes,
        sandbox=config.sandbox,
        state=state,
        prompt=prompt,
    )


def _seed_user_tokens(config: EbayConfig, auth: EbayAuth, tokens: OAuthTokens) -> None:
    """Make the freshly exchanged tokens usable by subsequent requests."""
    if tokens.refresh_token:
        config.refresh_token = tokens.refresh_token
    auth.cache.set(auth._cache_key(), tokens.to_token_data())


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
        self._owns_http = http_client is None
        self.http = http_client or httpx.Client(timeout=self.config.timeout)
        self.auth = EbayAuth(self.config, token_cache)
        self._transport = EbayTransport(self.config, self.auth, self.http)

        from .generated.resources import install_sync_namespaces

        install_sync_namespaces(self)

    @classmethod
    def from_env(cls) -> EbayClient:
        return cls(EbayConfig.from_env())

    def authorization_url(
        self,
        *,
        state: str | None = None,
        prompt: str | None = None,
        scopes: tuple[str, ...] | None = None,
    ) -> str:
        """Build the eBay consent URL to send a user to (authorization-code flow)."""
        return _authorization_url(self.config, state=state, prompt=prompt, scopes=scopes)

    def exchange_code(self, code: str, *, ru_name: str | None = None) -> OAuthTokens:
        """Exchange a consent ``code`` for tokens and authenticate this client with them."""
        tokens = self.auth.exchange_code(self.http, code, ru_name=ru_name)
        _seed_user_tokens(self.config, self.auth, tokens)
        return tokens

    def close(self) -> None:
        # Only close the transport the SDK created; never an injected, caller-owned client.
        if self._owns_http:
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
        self._owns_http = http_client is None
        self.http = http_client or httpx.AsyncClient(timeout=self.config.timeout)
        self.auth = EbayAuth(self.config, token_cache)
        self._transport = AsyncEbayTransport(self.config, self.auth, self.http)

        from .generated.resources import install_async_namespaces

        install_async_namespaces(self)

    @classmethod
    def from_env(cls) -> AsyncEbayClient:
        return cls(EbayConfig.from_env())

    def authorization_url(
        self,
        *,
        state: str | None = None,
        prompt: str | None = None,
        scopes: tuple[str, ...] | None = None,
    ) -> str:
        """Build the eBay consent URL to send a user to (authorization-code flow)."""
        return _authorization_url(self.config, state=state, prompt=prompt, scopes=scopes)

    async def exchange_code(self, code: str, *, ru_name: str | None = None) -> OAuthTokens:
        """Exchange a consent ``code`` for tokens and authenticate this client with them."""
        tokens = await self.auth.async_exchange_code(self.http, code, ru_name=ru_name)
        _seed_user_tokens(self.config, self.auth, tokens)
        return tokens

    async def close(self) -> None:
        # Only close the transport the SDK created; never an injected, caller-owned client.
        if self._owns_http:
            await self.http.aclose()

    async def __aenter__(self) -> AsyncEbayClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def request(self, **kwargs: Any) -> Any:
        return await self._transport.request(**kwargs)

    def stream(self, **kwargs: Any) -> AbstractAsyncContextManager[httpx.Response]:
        return self._transport.stream(**kwargs)
