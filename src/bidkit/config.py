from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

SecretValue = SecretStr | str


class EbaySigningConfig(BaseModel):
    """Credentials for eBay digital-signature (message signing).

    Required by the Finances API and several payout/refund operations. ``jwe`` is the
    encrypted public key returned by the Key Management API; ``private_key`` is the
    matching PEM (or bare base64 PKCS#8) private key; ``digest`` selects the
    content-digest algorithm.
    """

    model_config = ConfigDict(extra="forbid")

    jwe: str
    private_key: SecretValue
    digest: Literal["sha256", "sha512"] = "sha256"
    # Escape hatch: sign every request instead of only the operations eBay
    # requires signatures for, in case eBay expands the signed-API list before
    # the SDK catches up.
    sign_all: bool = False

    @property
    def private_key_value(self) -> str:
        value = _secret_value(self.private_key)
        if value is None:
            raise ValueError("signing private_key is empty")
        return value

    @classmethod
    def from_key_file(cls, path: str | Path) -> EbaySigningConfig:
        """Load signing material from an ebay-cli style ``signing-key.json``."""
        data = json.loads(Path(path).expanduser().read_text())
        private_key = data.get("privateKeyPem") or data.get("privateKey")
        if not data.get("jwe") or not private_key:
            raise ValueError(f"Signing key file {path} is missing 'jwe' and/or a private key")
        digest = data.get("cipher") or "sha256"
        return cls(jwe=data["jwe"], private_key=private_key, digest=digest)


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

    signing: EbaySigningConfig | None = None

    timeout: float = Field(default=30.0, gt=0)
    base_url_override: str | None = None

    # Retry policy for transient responses (429 + transient 5xx) and connection errors.
    max_retries: int = Field(default=2, ge=0)
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    retry_backoff: float = Field(default=0.5, ge=0)
    retry_max_backoff: float = Field(default=60.0, ge=0)
    respect_retry_after: bool = True

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

        signing_key_file = value("SIGNING_KEY_FILE")
        signing_jwe = value("SIGNING_JWE")
        if signing_key_file:
            data["signing"] = EbaySigningConfig.from_key_file(signing_key_file)
        else:
            signing_private_key = value("SIGNING_PRIVATE_KEY")
            if signing_jwe and signing_private_key:
                data["signing"] = EbaySigningConfig.model_validate(
                    {
                        "jwe": signing_jwe,
                        "private_key": signing_private_key,
                        "digest": value("SIGNING_DIGEST") or "sha256",
                    }
                )

        return cls(**{key: val for key, val in data.items() if val is not None})

    @classmethod
    def from_file(
        cls,
        path: str | Path = "~/.config/ebay-cli/config.json",
        *,
        signing_key_file: str | Path | None = None,
    ) -> EbayConfig:
        """Load an ebay-cli style ``config.json``.

        Credentials live under a ``credentials`` object (or at the top level) with the
        aliases ebay-cli uses: ``app_id``/``client_id``, ``cert_id``/``client_secret``,
        ``ru_name``/``redirect_uri``, ``granted_scopes``/``scopes``. Top-level
        ``environment`` ("sandbox"/"production") and ``marketplace_default`` map to
        ``sandbox`` and ``marketplace_id``. A ``signing-key.json`` next to the config is
        picked up automatically; pass ``signing_key_file`` to point elsewhere.
        """
        config_path = Path(path).expanduser()
        raw = json.loads(config_path.read_text())
        creds = raw.get("credentials", raw)
        if not isinstance(creds, dict):
            raise ValueError(f"Config file {config_path} has no usable 'credentials' object")

        def alias(*names: str) -> Any:
            return next((creds[name] for name in names if creds.get(name)), None)

        scopes = alias("granted_scopes", "scopes")
        data: dict[str, Any] = {
            "app_id": alias("app_id", "client_id"),
            "cert_id": alias("cert_id", "client_secret"),
            "dev_id": alias("dev_id"),
            "ru_name": alias("ru_name", "redirect_uri"),
            "refresh_token": alias("refresh_token"),
            "marketplace_id": raw.get("marketplace_default"),
        }
        if raw.get("environment"):
            data["sandbox"] = raw["environment"] == "sandbox"
        if scopes:
            data["scopes"] = tuple(scopes.split()) if isinstance(scopes, str) else tuple(scopes)

        if signing_key_file is None:
            sibling = config_path.with_name("signing-key.json")
            signing_key_file = sibling if sibling.exists() else None
        if signing_key_file is not None:
            data["signing"] = EbaySigningConfig.from_key_file(signing_key_file)

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
