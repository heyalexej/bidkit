import pytest

from bidkit.config import EbayConfig, EbaySigningConfig

ENV_VALUES = {
    "EBAY_APP_ID": "app-PRD-123",
    "EBAY_CERT_ID": "PRD-secret",
    "EBAY_DEV_ID": "dev-1",
    "EBAY_RU_NAME": "Ru-Name",
    "EBAY_MARKETPLACE_ID": "EBAY_DE",
    "EBAY_ACCEPT_LANGUAGE": "de-DE",
    "EBAY_CONTENT_LANGUAGE": "de-DE",
    "EBAY_REFRESH_TOKEN": "v^1.refresh",
    "EBAY_SCOPES": "https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/sell.finances",
    "EBAY_SANDBOX": "true",
}


def _clear_ebay_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for name in os.environ:
        if name.startswith("EBAY_"):
            monkeypatch.delenv(name)


def test_from_env_reads_all_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_ebay_env(monkeypatch)
    for name, value in ENV_VALUES.items():
        monkeypatch.setenv(name, value)

    config = EbayConfig.from_env()

    assert config.app_id == "app-PRD-123"
    assert config.client_secret == "PRD-secret"
    assert config.dev_id == "dev-1"
    assert config.ru_name == "Ru-Name"
    assert config.marketplace_id == "EBAY_DE"
    assert config.accept_language == "de-DE"
    assert config.content_language == "de-DE"
    assert config.refresh_token_value == "v^1.refresh"
    assert config.scopes == (
        "https://api.ebay.com/oauth/api_scope",
        "https://api.ebay.com/oauth/api_scope/sell.finances",
    )
    assert config.sandbox is True


def test_from_env_defaults_and_empty_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_ebay_env(monkeypatch)
    monkeypatch.setenv("EBAY_APP_ID", "")  # empty counts as unset

    config = EbayConfig.from_env()

    assert config.app_id is None
    assert config.marketplace_id == "EBAY_US"
    assert config.sandbox is False
    assert config.scopes == ("https://api.ebay.com/oauth/api_scope",)


def test_from_env_reads_signing_material(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_ebay_env(monkeypatch)
    monkeypatch.setenv("EBAY_SIGNING_JWE", "jwe-value")
    monkeypatch.setenv("EBAY_SIGNING_PRIVATE_KEY", "base64-key")
    monkeypatch.setenv("EBAY_SIGNING_DIGEST", "sha512")

    config = EbayConfig.from_env()

    assert config.signing is not None
    assert config.signing.jwe == "jwe-value"
    assert config.signing.private_key_value == "base64-key"
    assert config.signing.digest == "sha512"


def test_from_env_signing_key_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    _clear_ebay_env(monkeypatch)
    key_file = tmp_path_factory.mktemp("keys") / "signing-key.json"
    key_file.write_text('{"jwe": "jwe-from-file", "privateKeyPem": "pem-body"}')
    monkeypatch.setenv("EBAY_SIGNING_KEY_FILE", str(key_file))

    config = EbayConfig.from_env()

    assert config.signing is not None
    assert config.signing.jwe == "jwe-from-file"
    assert config.signing.private_key_value == "pem-body"


def test_signing_key_file_requires_jwe_and_key(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    key_file = tmp_path_factory.mktemp("keys") / "incomplete.json"
    key_file.write_text('{"jwe": "only-jwe"}')

    with pytest.raises(ValueError, match="missing"):
        EbaySigningConfig.from_key_file(key_file)


def test_from_file_reads_ebay_cli_config(tmp_path_factory: pytest.TempPathFactory) -> None:
    config_dir = tmp_path_factory.mktemp("ebay-cli")
    (config_dir / "config.json").write_text(
        """
        {
          "environment": "sandbox",
          "marketplace_default": "EBAY_DE",
          "credentials": {
            "client_id": "app-SBX-1",
            "client_secret": "secret",
            "redirect_uri": "Ru-Name",
            "refresh_token": "v^1.refresh",
            "granted_scopes": "https://api.ebay.com/oauth/api_scope scope-b"
          }
        }
        """
    )
    (config_dir / "signing-key.json").write_text('{"jwe": "jwe-x", "privateKeyPem": "pem-x"}')

    config = EbayConfig.from_file(config_dir / "config.json")

    assert config.app_id == "app-SBX-1"
    assert config.client_secret == "secret"
    assert config.ru_name == "Ru-Name"
    assert config.refresh_token_value == "v^1.refresh"
    assert config.sandbox is True
    assert config.marketplace_id == "EBAY_DE"
    assert config.scopes == ("https://api.ebay.com/oauth/api_scope", "scope-b")
    assert config.signing is not None
    assert config.signing.jwe == "jwe-x"


def test_from_file_canonical_names_and_defaults(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    config_dir = tmp_path_factory.mktemp("ebay-cli")
    (config_dir / "config.json").write_text(
        '{"credentials": {"app_id": "app-PRD-1", "cert_id": "c", "scopes": ["s1", "s2"]}}'
    )

    config = EbayConfig.from_file(config_dir / "config.json")

    assert config.app_id == "app-PRD-1"
    assert config.sandbox is False
    assert config.marketplace_id == "EBAY_US"
    assert config.scopes == ("s1", "s2")
    assert config.signing is None  # no sibling signing-key.json


def test_from_file_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        EbayConfig.from_file("/nonexistent/config.json")


def test_api_root_and_oauth_url_respect_sandbox_and_override() -> None:
    prod = EbayConfig()
    sandbox = EbayConfig(sandbox=True)
    overridden = EbayConfig(base_url_override="http://localhost:9000/")

    assert prod.api_root("apiz") == "https://apiz.ebay.com"
    assert sandbox.api_root() == "https://api.sandbox.ebay.com"
    assert sandbox.oauth_token_url == "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
    assert overridden.api_root("apiz") == "http://localhost:9000"
