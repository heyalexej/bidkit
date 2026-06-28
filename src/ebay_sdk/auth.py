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

    def _parse_token_response(self, response: httpx.Response) -> TokenData:
        if response.status_code >= 400:
            try:
                detail = orjson.loads(response.content)
            except orjson.JSONDecodeError:
                detail = response.text
            raise EbayAuthError(f"OAuth token request failed: {detail}")

        payload = orjson.loads(response.content)
        access_token = payload.get("access_token")
        if not access_token:
            raise EbayAuthError("OAuth token response did not include access_token")
        expires_in = int(payload.get("expires_in", 7200))
        return TokenData(
            access_token=access_token,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            token_type=payload.get("token_type", "Bearer"),
        )
