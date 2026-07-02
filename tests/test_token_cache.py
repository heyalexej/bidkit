import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from bidkit import EbayClient, EbayConfig, FileTokenCache
from bidkit.auth import TokenData


def _token(expires_in_s: int = 3600) -> TokenData:
    return TokenData(
        access_token="tok-value",
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_s),
    )


def test_round_trip_and_restrictive_permissions(tmp_path: Path) -> None:
    cache = FileTokenCache(tmp_path / "tokens.json")
    cache.set("key-1", _token())

    loaded = cache.get("key-1")
    assert loaded is not None
    assert loaded.access_token == "tok-value"
    mode = stat.S_IMODE((tmp_path / "tokens.json").stat().st_mode)
    assert mode == 0o600


def test_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    FileTokenCache(path).set("key-1", _token())

    assert FileTokenCache(path).get("key-1") is not None
    assert FileTokenCache(path).get("other") is None


def test_corrupt_file_is_treated_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text("not json{")
    cache = FileTokenCache(path)

    assert cache.get("key-1") is None
    cache.set("key-1", _token())
    assert cache.get("key-1") is not None


def test_expired_entries_are_pruned_on_write(tmp_path: Path) -> None:
    cache = FileTokenCache(tmp_path / "tokens.json")
    cache.set("dead", _token(expires_in_s=-60))
    cache.set("live", _token())

    assert cache.get("dead") is None
    assert "dead" not in (tmp_path / "tokens.json").read_text()
    assert cache.get("live") is not None


def test_naive_expires_at_entries_do_not_crash(tmp_path: Path) -> None:
    """Foreign tools may write tz-naive timestamps; both get() and set() must survive."""
    path = tmp_path / "tokens.json"
    path.write_text('{"foreign": {"access_token": "a", "expires_at": "2099-01-01T00:00:00"}}')
    cache = FileTokenCache(path)

    loaded = cache.get("foreign")
    assert loaded is not None
    assert loaded.expires_at.tzinfo is not None  # pinned to UTC
    assert loaded.is_stale is False
    cache.set("mine", _token())  # prune pass over the naive entry must not raise
    assert cache.get("mine") is not None


def test_get_serves_from_snapshot_until_file_changes(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    cache = FileTokenCache(path)
    cache.set("key-1", _token())
    assert cache.get("key-1") is not None

    reads = {"n": 0}
    original = Path.read_bytes

    def counting_read(self: Path) -> bytes:
        reads["n"] += 1
        return original(self)

    Path.read_bytes = counting_read  # type: ignore[method-assign]
    try:
        for _ in range(5):
            assert cache.get("key-1") is not None
        assert reads["n"] == 0  # unchanged file -> served from the stat-validated snapshot

        FileTokenCache(path).set("key-2", _token())  # external write changes mtime/size
        assert cache.get("key-2") is not None
        assert reads["n"] >= 1  # snapshot invalidated, file re-read once
    finally:
        Path.read_bytes = original  # type: ignore[method-assign]


def test_second_client_reuses_persisted_token_without_oauth_call(tmp_path: Path) -> None:
    token_requests = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            token_requests["n"] += 1
            return httpx.Response(200, json={"access_token": "minted", "expires_in": 7200})
        return httpx.Response(200, json={})

    def make_client() -> EbayClient:
        return EbayClient(
            EbayConfig(app_id="app", cert_id="cert", refresh_token="refresh"),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            token_cache=FileTokenCache(tmp_path / "tokens.json"),
        )

    make_client().buy.browse.get_item("v1|1|0", raw_response=True)
    make_client().buy.browse.get_item("v1|1|0", raw_response=True)

    assert token_requests["n"] == 1
