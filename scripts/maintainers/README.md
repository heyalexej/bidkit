# Maintainer scripts

These scripts hit eBay **production** with real credentials and are used for pre-release
smoke testing; they are not part of the SDK's public surface.

- `live_smoke.py` — broad read-only smoke across all wired APIs.
- `smoke_de.py` — read-only smoke against a real seller account on EBAY_DE.

Both read an ebay-cli style config from `~/.config/ebay-cli/config.json` (see
[`examples/`](../../examples/) for templates) and require a seller `refresh_token` minted
with `scripts/oauth_login.py`. Run with `uv run --extra dev scripts/maintainers/<name>.py`.
