from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlencode

import httpx
import orjson
from pydantic import BaseModel

from .config import EbayConfig
from .errors import EbayAuthError, EbayConfigError


class TokenData(BaseModel):
    access_token: str
    expires_at: datetime
    token_type: str = "Bearer"

    @property
    def is_stale(self) -> bool:
        return self.expires_at <= datetime.now(UTC) + timedelta(minutes=5)


class OAuthTokens(BaseModel):
    """Result of an authorization-code exchange.

    ``refresh_token`` is the long-lived credential to persist and pass back as
    ``EbayConfig.refresh_token``; ``access_token`` is the short-lived user token.
    """

    access_token: str
    token_expiry: datetime
    refresh_token: str | None = None
    refresh_token_expiry: datetime | None = None
    token_type: str = "User Access Token"

    def to_token_data(self) -> TokenData:
        return TokenData(
            access_token=self.access_token,
            expires_at=self.token_expiry,
            token_type=self.token_type,
        )


class TokenCache(Protocol):
    def get(self, key: str) -> TokenData | None: ...

    def set(self, key: str, token: TokenData) -> None: ...


@dataclass
class InMemoryTokenCache:
    _tokens: dict[str, TokenData]

    def __init__(self) -> None:
        self._tokens = {}

    def get(self, key: str) -> TokenData | None:
        return self._tokens.get(key)

    def set(self, key: str, token: TokenData) -> None:
        self._tokens[key] = token


class EbayAuth:
    def __init__(self, config: EbayConfig, cache: TokenCache | None = None) -> None:
        self.config = config
        self.cache = cache or InMemoryTokenCache()

    @staticmethod
    def authorization_url(
        *,
        app_id: str,
        ru_name: str,
        scopes: tuple[str, ...],
        sandbox: bool = False,
        state: str | None = None,
        prompt: str | None = None,
    ) -> str:
        host = "auth.sandbox.ebay.com" if sandbox else "auth.ebay.com"
        query = {
            "client_id": app_id,
            "redirect_uri": ru_name,
            "response_type": "code",
            "scope": " ".join(scopes),
        }
        if state:
            query["state"] = state
        if prompt:
            query["prompt"] = prompt
        return f"https://{host}/oauth2/authorize?{urlencode(query)}"

    def exchange_code(
        self,
        client: httpx.Client,
        code: str,
        *,
        ru_name: str | None = None,
    ) -> OAuthTokens:
        """Exchange an authorization code for user access + refresh tokens."""
        response = client.post(
            self.config.oauth_token_url,
            data=self._exchange_data(code, ru_name),
            auth=self._client_credentials(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return self._parse_oauth_tokens(response)

    async def async_exchange_code(
        self,
        client: httpx.AsyncClient,
        code: str,
        *,
        ru_name: str | None = None,
    ) -> OAuthTokens:
        response = await client.post(
            self.config.oauth_token_url,
            data=self._exchange_data(code, ru_name),
            auth=self._client_credentials(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return self._parse_oauth_tokens(response)

    def _exchange_data(self, code: str, ru_name: str | None) -> dict[str, str]:
        redirect_uri = ru_name or self.config.ru_name
        if not redirect_uri:
            raise EbayConfigError("ru_name is required to exchange an authorization code")
        return {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }

    def authorization_header(
        self,
        client: httpx.Client,
        *,
        scheme: str = "Bearer",
    ) -> dict[str, str]:
        return {"Authorization": f"{scheme} {self.access_token(client)}"}

    async def async_authorization_header(
        self,
        client: httpx.AsyncClient,
        *,
        scheme: str = "Bearer",
    ) -> dict[str, str]:
        return {"Authorization": f"{scheme} {await self.async_access_token(client)}"}

    def access_token(self, client: httpx.Client) -> str:
        static_token = self.config.bearer_token
        if static_token:
            return static_token

        cached = self.cache.get(self._cache_key())
        if cached and not cached.is_stale:
            return cached.access_token

        token = (
            self._refresh_user_token(client)
            if self.config.refresh_token
            else self._client_token(client)
        )
        self.cache.set(self._cache_key(), token)
        return token.access_token

    async def async_access_token(self, client: httpx.AsyncClient) -> str:
        static_token = self.config.bearer_token
        if static_token:
            return static_token

        cached = self.cache.get(self._cache_key())
        if cached and not cached.is_stale:
            return cached.access_token

        token = (
            await self._async_refresh_user_token(client)
            if self.config.refresh_token
            else await self._async_client_token(client)
        )
        self.cache.set(self._cache_key(), token)
        return token.access_token

    def _cache_key(self) -> str:
        kind = "refresh" if self.config.refresh_token else "client"
        return f"{kind}:{self.config.sandbox}:{' '.join(self.config.scopes)}"

    def _client_token(self, client: httpx.Client) -> TokenData:
        client_auth = self._client_credentials()
        response = client.post(
            self.config.oauth_token_url,
            data={
                "grant_type": "client_credentials",
                "scope": " ".join(self.config.scopes),
            },
            auth=client_auth,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return self._parse_token_response(response)

    async def _async_client_token(self, client: httpx.AsyncClient) -> TokenData:
        client_auth = self._client_credentials()
        response = await client.post(
            self.config.oauth_token_url,
            data={
                "grant_type": "client_credentials",
                "scope": " ".join(self.config.scopes),
            },
            auth=client_auth,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return self._parse_token_response(response)

    def _refresh_user_token(self, client: httpx.Client) -> TokenData:
        client_auth = self._client_credentials()
        refresh_token = self._refresh_token()
        response = client.post(
            self.config.oauth_token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": " ".join(self.config.scopes),
            },
            auth=client_auth,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return self._parse_token_response(response)

    async def _async_refresh_user_token(self, client: httpx.AsyncClient) -> TokenData:
        client_auth = self._client_credentials()
        refresh_token = self._refresh_token()
        response = await client.post(
            self.config.oauth_token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": " ".join(self.config.scopes),
            },
            auth=client_auth,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return self._parse_token_response(response)

    def _client_credentials(self) -> tuple[str, str]:
        client_secret = self.config.client_secret
        if not self.config.app_id or not client_secret:
            raise EbayConfigError("app_id and cert_id are required to obtain OAuth tokens")
        return self.config.app_id, client_secret

    def _refresh_token(self) -> str:
        refresh_token = self.config.refresh_token_value
        if not refresh_token:
            raise EbayConfigError("refresh_token is required to refresh a user token")
        return refresh_token

    def _decode_token_response(self, response: httpx.Response) -> dict:
        if response.status_code >= 400:
            try:
                detail = orjson.loads(response.content)
            except orjson.JSONDecodeError:
                detail = response.text
            raise EbayAuthError(f"OAuth token request failed: {detail}")

        payload = orjson.loads(response.content)
        if not payload.get("access_token"):
            raise EbayAuthError("OAuth token response did not include access_token")
        return payload

    def _parse_token_response(self, response: httpx.Response) -> TokenData:
        payload = self._decode_token_response(response)
        expires_in = int(payload.get("expires_in", 7200))
        return TokenData(
            access_token=payload["access_token"],
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            token_type=payload.get("token_type", "Bearer"),
        )

    def _parse_oauth_tokens(self, response: httpx.Response) -> OAuthTokens:
        payload = self._decode_token_response(response)
        now = datetime.now(UTC)
        refresh_expiry = None
        if payload.get("refresh_token_expires_in") is not None:
            refresh_expiry = now + timedelta(seconds=int(payload["refresh_token_expires_in"]))
        return OAuthTokens(
            access_token=payload["access_token"],
            token_expiry=now + timedelta(seconds=int(payload.get("expires_in", 7200))),
            refresh_token=payload.get("refresh_token"),
            refresh_token_expiry=refresh_expiry,
            token_type=payload.get("token_type", "User Access Token"),
        )
