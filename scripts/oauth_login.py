"""Mint an eBay user refresh token from the CLI via the authorization-code flow.

Opens the system browser for consent, then exchanges the redirected ``code`` for tokens.
eBay redirects to your RuName's registered HTTPS "accepted URL"; copy that URL from the
browser's address bar and paste it back here (the ``code`` is in its query string).

    uv run --extra dev scripts/oauth_login.py
    uv run --extra dev scripts/oauth_login.py --sandbox --no-browser

Credentials are read from the ebay-cli config (~/.config/ebay-cli/config.json) by default;
override with --app-id/--cert-id/--ru-name/--scopes.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bidkit import EbayClient, EbayConfig, OAuthTokens  # noqa: E402
from bidkit.errors import EbayAuthError, EbayConfigError  # noqa: E402


def write_tokens_to_config(path: Path, tokens: OAuthTokens) -> None:
    """Persist the minted tokens and their expiries into an ebay-cli style config file.

    Existing fields (app_id, scopes, ...) are preserved; only token/expiry fields change.
    """
    data: dict = json.loads(path.read_text()) if path.exists() else {}
    creds = data.setdefault("credentials", {})
    creds["refresh_token"] = tokens.refresh_token
    creds["access_token"] = tokens.access_token
    creds["token_type"] = tokens.token_type
    creds["access_token_expiry"] = tokens.token_expiry.isoformat()
    if tokens.refresh_token_expiry is not None:
        creds["refresh_token_expiry"] = tokens.refresh_token_expiry.isoformat()

    # Keep any pre-existing metadata block's expiry fields consistent.
    meta = data.get("metadata")
    if isinstance(meta, dict):
        meta["access_token_expires_at"] = tokens.token_expiry.isoformat()
        meta["access_token_expires_at_epoch"] = int(tokens.token_expiry.timestamp())
        if tokens.refresh_token_expiry is not None:
            meta["refresh_token_expires_at"] = tokens.refresh_token_expiry.isoformat()
            meta["refresh_token_expires_at_epoch"] = int(tokens.refresh_token_expiry.timestamp())

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def extract_code(pasted: str) -> str:
    """Pull the OAuth ``code`` out of a pasted redirect URL (or accept a raw code)."""
    pasted = pasted.strip()
    if pasted.lower().startswith("http"):
        query = parse_qs(urlsplit(pasted).query)
        if "code" not in query:
            raise SystemExit("No 'code' parameter found in the pasted URL.")
        return query["code"][0]
    # A bare code copied from the address bar is usually still percent-encoded.
    return unquote(pasted)


def keyset_env(app_id: str) -> str | None:
    """eBay App IDs encode the environment as a segment: ...-PRD-... or ...-SBX-..."""
    parts = app_id.split("-")
    if "SBX" in parts:
        return "sandbox"
    if "PRD" in parts:
        return "production"
    return None


def load_config(args: argparse.Namespace) -> EbayConfig:
    creds: dict = {}
    config_path = Path(args.config).expanduser()
    if config_path.exists():
        raw = json.loads(config_path.read_text())
        creds = raw.get("credentials", raw)

    app_id = args.app_id or creds.get("app_id") or creds.get("client_id")
    cert_id = args.cert_id or creds.get("cert_id") or creds.get("client_secret")
    ru_name = args.ru_name or creds.get("ru_name") or creds.get("redirect_uri")
    if args.scopes:
        scopes = tuple(args.scopes.split())
    else:
        granted = creds.get("granted_scopes") or creds.get("scopes") or []
        scopes = tuple(granted.split()) if isinstance(granted, str) else tuple(granted)

    if not (app_id and cert_id and ru_name and scopes):
        raise SystemExit("Need app_id, cert_id, ru_name and scopes (via config or flags).")

    return EbayConfig(
        app_id=app_id,
        cert_id=cert_id,
        ru_name=ru_name,
        scopes=scopes,
        marketplace_id=args.marketplace,
        sandbox=args.sandbox,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="~/.config/ebay-cli/config.json")
    parser.add_argument("--app-id")
    parser.add_argument("--cert-id")
    parser.add_argument("--ru-name")
    parser.add_argument("--scopes", help="space-separated scope list")
    parser.add_argument("--marketplace", default="EBAY_DE")
    parser.add_argument("--sandbox", action="store_true")
    parser.add_argument(
        "--no-browser", action="store_true", help="print the URL instead of opening it"
    )
    parser.add_argument(
        "--redirect-url",
        help="the full URL eBay redirected to after consent (skips the interactive prompt)",
    )
    parser.add_argument("--code", help="the authorization code itself (skips the prompt)")
    parser.add_argument(
        "--write-config",
        action="store_true",
        help="write the minted tokens + expiries back into --config",
    )
    args = parser.parse_args()

    config = load_config(args)

    env = keyset_env(config.app_id or "")
    if env == "production" and args.sandbox:
        raise SystemExit(
            f"App ID '{config.app_id}' is a PRODUCTION keyset (-PRD-), but --sandbox was set, "
            "which authenticates against eBay's sandbox and fails with 'invalid_client'. "
            "Drop --sandbox, or use a sandbox (-SBX-) keyset."
        )
    if env == "sandbox" and not args.sandbox:
        raise SystemExit(
            f"App ID '{config.app_id}' is a SANDBOX keyset (-SBX-); add --sandbox."
        )

    client = EbayClient(config)

    # If the code was supplied up front, exchange straight away (no browser, no prompt).
    if args.code or args.redirect_url:
        code = args.code or extract_code(args.redirect_url or "")
    else:
        try:
            url = client.authorization_url(state="cli")
        except EbayConfigError as exc:
            raise SystemExit(str(exc)) from exc

        print("\n1) Grant consent in your browser:")
        print(f"   {url}\n")
        if not args.no_browser:
            webbrowser.open(url)

        print("2) After consent, eBay redirects to your RuName's accepted URL.")
        print("   Copy that URL from the address bar and paste it here (then press Enter).")
        print("   Tip: you can also re-run with --redirect-url '<that url>' to skip this prompt.")
        try:
            pasted = input("\n   redirect URL or code> ").strip()
        except EOFError:
            raise SystemExit(
                "\nNo input received. Re-run passing the value directly:\n"
                "   uv run --extra dev scripts/oauth_login.py --redirect-url '<pasted url>'"
            ) from None
        if not pasted:
            raise SystemExit("No redirect URL or code provided.")
        code = extract_code(pasted)

    try:
        tokens = client.exchange_code(code)
    except EbayAuthError as exc:
        raise SystemExit(f"Exchange failed: {exc}") from exc
    finally:
        client.close()

    print("\n3) Success. Persist this refresh token as EbayConfig(refresh_token=...):\n")
    print(f"   refresh_token: {tokens.refresh_token}")
    print(f"   refresh_token_expiry: {tokens.refresh_token_expiry}")
    print(f"   access_token (short-lived): {tokens.access_token[:24]}...")

    if args.write_config:
        target = Path(args.config).expanduser()
        write_tokens_to_config(target, tokens)
        print(f"\n   wrote refresh_token + expiries to {target}")


if __name__ == "__main__":
    main()
