from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx
import orjson
from pydantic import BaseModel, ValidationError

from .config import EbayConfig
from .errors import EbayAuthError, EbayConfigError

logger = logging.getLogger("bidkit.auth")


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


class FileTokenCache:
    """Persist access tokens across processes in a 0600 JSON file.

    Drop-in :class:`TokenCache`::

        client = EbayClient(config, token_cache=FileTokenCache())

    Defaults to ``$XDG_CACHE_HOME/bidkit/tokens.json`` (``~/.cache/bidkit/tokens.json``).
    Each entry maps an :meth:`EbayAuth._cache_key` (which never contains token values) to
    the token data; the file itself holds live access tokens, hence the restrictive mode.
    Writes are atomic and expired entries are pruned on every write; a corrupt or foreign
    file is treated as empty rather than raising.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            cache_home = os.environ.get("XDG_CACHE_HOME") or "~/.cache"
            path = Path(cache_home) / "bidkit" / "tokens.json"
        self.path = Path(path).expanduser()
        self._lock = threading.Lock()

    def get(self, key: str) -> TokenData | None:
        with self._lock:
            entry = self._load().get(key)
        if not isinstance(entry, dict):
            return None
        try:
            return TokenData.model_validate(entry)
        except ValidationError:
            return None

    def set(self, key: str, token: TokenData) -> None:
        with self._lock:
            entries = self._load()
            entries[key] = token.model_dump(mode="json")
            entries = {k: v for k, v in entries.items() if self._is_live(v)}
            self._write(entries)

    @staticmethod
    def _is_live(entry: Any) -> bool:
        try:
            return TokenData.model_validate(entry).expires_at > datetime.now(UTC)
        except ValidationError:
            return False

    def _load(self) -> dict[str, Any]:
        try:
            data = orjson.loads(self.path.read_bytes())
        except (OSError, orjson.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, entries: dict[str, Any]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + f".{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(orjson.dumps(entries, option=orjson.OPT_INDENT_2))
            os.replace(tmp, self.path)  # atomic; inherits the 0600 mode
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise


class EbayAuth:
    def __init__(self, config: EbayConfig, cache: TokenCache | None = None) -> None:
        self.config = config
        self.cache = cache or InMemoryTokenCache()
        # Serialize token refreshes per cache key so concurrent callers hitting a stale
        # token trigger a single refresh instead of a stampede on the OAuth endpoint. The
        # sync and async paths use their own primitive; _locks_guard protects the lazy
        # creation of both maps.
        self._locks_guard = threading.Lock()
        self._sync_locks: dict[str, threading.Lock] = {}
        self._async_locks: dict[str, asyncio.Lock] = {}

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

        key = self._cache_key()
        cached = self.cache.get(key)
        if cached and not cached.is_stale:
            return cached.access_token

        with self._sync_lock(key):
            # Re-check inside the lock: another thread may have refreshed while we waited.
            cached = self.cache.get(key)
            if cached and not cached.is_stale:
                return cached.access_token
            token = (
                self._refresh_user_token(client)
                if self.config.refresh_token
                else self._client_token(client)
            )
            self.cache.set(key, token)
            self._log_token_acquired(token)
            return token.access_token

    async def async_access_token(self, client: httpx.AsyncClient) -> str:
        static_token = self.config.bearer_token
        if static_token:
            return static_token

        key = self._cache_key()
        cached = self.cache.get(key)
        if cached and not cached.is_stale:
            return cached.access_token

        async with self._async_lock(key):
            # Re-check inside the lock: another coroutine may have refreshed while we waited.
            cached = self.cache.get(key)
            if cached and not cached.is_stale:
                return cached.access_token
            token = (
                await self._async_refresh_user_token(client)
                if self.config.refresh_token
                else await self._async_client_token(client)
            )
            self.cache.set(key, token)
            self._log_token_acquired(token)
            return token.access_token

    def _log_token_acquired(self, token: TokenData) -> None:
        """Log token acquisition without ever touching the token values themselves."""
        if not logger.isEnabledFor(logging.INFO):
            return
        expires_in = int((token.expires_at - datetime.now(UTC)).total_seconds())
        if self.config.refresh_token:
            digest = hashlib.sha256((self.config.refresh_token_value or "").encode()).hexdigest()
            logger.info(
                "refreshed user token for refresh:%s… (expires in %d s)",
                digest[:8],
                expires_in,
                extra={"grant": "user", "expires_in": expires_in},
            )
        else:
            logger.info(
                "minted client token (expires in %d s)",
                expires_in,
                extra={"grant": "client", "expires_in": expires_in},
            )

    def _sync_lock(self, key: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._sync_locks.get(key)
            if lock is None:
                lock = self._sync_locks[key] = threading.Lock()
            return lock

    def _async_lock(self, key: str) -> asyncio.Lock:
        with self._locks_guard:
            lock = self._async_locks.get(key)
            if lock is None:
                lock = self._async_locks[key] = asyncio.Lock()
            return lock

    def _cache_key(self) -> str:
        # Identify the exact grant so a shared cache never returns another tenant's token:
        # app credentials + the specific refresh token (hashed, not stored) + env + scopes.
        if self.config.refresh_token:
            digest = hashlib.sha256((self.config.refresh_token_value or "").encode()).hexdigest()
            grant = f"refresh:{digest[:16]}"
        else:
            grant = "client"
        env = "sandbox" if self.config.sandbox else "production"
        app_id = self.config.app_id or "-"
        return f"{grant}:{app_id}:{env}:{' '.join(self.config.scopes)}"

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
