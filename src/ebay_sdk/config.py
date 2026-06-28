from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr

SecretValue = SecretStr | str


class EbayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_id: str | None = None
    cert_id: SecretValue | None = None
    dev_id: str | None = None
    ru_name: str | None = None
    sandbox: bool = False

    marketplace_id: str = "EBAY_US"
    accept_language: str | None = "en-US"
    content_language: str | None = "en-US"

    access_token: SecretValue | None = None
    refresh_token: SecretValue | None = None
    scopes: tuple[str, ...] = ("https://api.ebay.com/oauth/api_scope",)
    auto_refresh: bool = True

    timeout: float = Field(default=30.0, gt=0)
    base_url_override: str | None = None

    @classmethod
    def from_env(cls, prefix: str = "EBAY_") -> EbayConfig:
        def value(name: str) -> str | None:
            raw = os.getenv(prefix + name)
            return raw if raw not in (None, "") else None

        scopes = value("SCOPES")
        data: dict[str, Any] = {
            "app_id": value("APP_ID"),
            "cert_id": value("CERT_ID"),
            "dev_id": value("DEV_ID"),
            "ru_name": value("RU_NAME"),
            "marketplace_id": value("MARKETPLACE_ID") or "EBAY_US",
            "accept_language": value("ACCEPT_LANGUAGE") or "en-US",
            "content_language": value("CONTENT_LANGUAGE") or "en-US",
            "access_token": value("ACCESS_TOKEN"),
            "refresh_token": value("REFRESH_TOKEN"),
            "base_url_override": value("BASE_URL"),
        }
        if value("SANDBOX") is not None:
            data["sandbox"] = value("SANDBOX") in {"1", "true", "TRUE", "yes", "YES"}
        if scopes:
            data["scopes"] = tuple(scope for scope in scopes.split() if scope)
        return cls(**{key: val for key, val in data.items() if val is not None})

    def api_root(self, subdomain: str = "api") -> str:
        if self.base_url_override:
            return self.base_url_override.rstrip("/")
        sandbox = ".sandbox" if self.sandbox else ""
        return f"https://{subdomain}{sandbox}.ebay.com"

    @property
    def oauth_token_url(self) -> str:
        return f"{self.api_root('api')}/identity/v1/oauth2/token"

    @property
    def client_secret(self) -> str | None:
        return _secret_value(self.cert_id)

    @property
    def bearer_token(self) -> str | None:
        return _secret_value(self.access_token)

    @property
    def refresh_token_value(self) -> str | None:
        return _secret_value(self.refresh_token)


def _secret_value(value: SecretValue | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return value
