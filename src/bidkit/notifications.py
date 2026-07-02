"""Verify inbound eBay push notifications (Notification API).

eBay signs every push notification — including the mandatory marketplace-account-deletion
notifications — with an ECDSA key identified by the ``x-ebay-signature`` request header:
a Base64-encoded JSON object ``{"alg": "ecdsa", "kid": "<key id>", "signature": "<Base64
DER ECDSA>", "digest": "SHA1"}``. The matching public key comes from the Notification
API's ``getPublicKey`` endpoint and should be cached (eBay recommends about an hour).

The signature covers the **raw request body bytes** — verify before parsing, and never
against a re-serialized payload.

Typical endpoint (framework-agnostic)::

    verifier = NotificationVerifier(client)

    # GET ?challenge_code=... -> endpoint validation
    return 200, challenge_response(challenge_code, VERIFICATION_TOKEN, ENDPOINT_URL)

    # POST -> notification delivery
    if verifier.verify(raw_body, request.headers["x-ebay-signature"]):
        return 204          # acknowledged
    return 412              # eBay retries on Precondition Failed
"""

from __future__ import annotations

import base64
import hashlib
import threading
import time
from typing import TYPE_CHECKING, Any

import orjson
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

if TYPE_CHECKING:
    from .client import AsyncEbayClient, EbayClient

_BASE_SCOPE = "https://api.ebay.com/oauth/api_scope"
_BEGIN = "-----BEGIN PUBLIC KEY-----"
_END = "-----END PUBLIC KEY-----"
_DIGESTS: dict[str, type[hashes.HashAlgorithm]] = {
    "SHA1": hashes.SHA1,
    "SHA256": hashes.SHA256,
}


def challenge_response(
    challenge_code: str, verification_token: str, endpoint: str
) -> dict[str, str]:
    """The body eBay expects back from the endpoint-validation ``GET ?challenge_code=…``.

    The hash input order is fixed by eBay: challenge code, then your verification token,
    then the endpoint URL exactly as registered. Return it as JSON with a 200 status and
    ``Content-Type: application/json``.
    """
    digest = hashlib.sha256(
        (challenge_code + verification_token + endpoint).encode("utf-8")
    ).hexdigest()
    return {"challengeResponse": digest}


def _decode_signature_header(header: str) -> tuple[str, bytes] | None:
    """Extract ``(kid, DER signature)`` from ``x-ebay-signature``, or None if malformed."""
    try:
        payload = orjson.loads(base64.b64decode(header))
        return str(payload["kid"]), base64.b64decode(payload["signature"])
    except (KeyError, TypeError, ValueError, orjson.JSONDecodeError):
        return None


def _load_public_key(
    key: str | None, digest: str | None
) -> tuple[ec.EllipticCurvePublicKey, hashes.HashAlgorithm]:
    """Parse the getPublicKey response into a key + hash pair."""
    if not key:
        raise ValueError("getPublicKey returned no key material")
    # eBay returns the PEM armor and Base64 body on a single line; re-insert newlines,
    # but leave keys that already contain them untouched.
    pem = key if "\n" in key else key.replace(_BEGIN, _BEGIN + "\n").replace(_END, "\n" + _END)
    public_key = serialization.load_pem_public_key(pem.encode("ascii"))
    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        raise TypeError(f"Expected an ECDSA public key, got {type(public_key).__name__}")
    hash_cls = _DIGESTS.get((digest or "SHA1").upper())
    if hash_cls is None:
        raise ValueError(f"Unsupported notification digest: {digest!r}")
    return public_key, hash_cls()


def _verify(
    key_and_hash: tuple[ec.EllipticCurvePublicKey, hashes.HashAlgorithm],
    signature: bytes,
    body: bytes,
) -> bool:
    public_key, hash_alg = key_and_hash
    try:
        public_key.verify(signature, body, ec.ECDSA(hash_alg))
        return True
    except InvalidSignature:
        return False


class _KeyCache:
    """TTL cache for parsed public keys, keyed by eBay's ``kid``."""

    def __init__(self, ttl: float) -> None:
        self._ttl = ttl
        self._lock = threading.Lock()
        self._entries: dict[
            str, tuple[float, tuple[ec.EllipticCurvePublicKey, hashes.HashAlgorithm]]
        ] = {}

    def get(self, kid: str) -> tuple[ec.EllipticCurvePublicKey, hashes.HashAlgorithm] | None:
        with self._lock:
            entry = self._entries.get(kid)
            if entry is None or entry[0] < time.monotonic():
                return None
            return entry[1]

    def set(self, kid: str, value: tuple[ec.EllipticCurvePublicKey, hashes.HashAlgorithm]) -> None:
        with self._lock:
            self._entries[kid] = (time.monotonic() + self._ttl, value)


def _app_scoped(client: Any) -> Any:
    """getPublicKey is an application-token method; scope the key-fetch client down to
    client credentials + the base scope whenever app credentials are available, so a
    seller (user-token) client can be wired in without its grant breaking key fetches."""
    config = client.config
    if config.app_id and config.client_secret:
        return client.with_options(refresh_token=None, access_token=None, scopes=(_BASE_SCOPE,))
    return client


class _VerifierBase:
    def __init__(self, cache_ttl: float) -> None:
        self._cache = _KeyCache(cache_ttl)

    def _cached(self, kid: str) -> tuple[ec.EllipticCurvePublicKey, hashes.HashAlgorithm] | None:
        return self._cache.get(kid)

    def _resolve(
        self, kid: str, response: Any
    ) -> tuple[ec.EllipticCurvePublicKey, hashes.HashAlgorithm]:
        key_and_hash = _load_public_key(response.key, response.digest)
        self._cache.set(kid, key_and_hash)
        return key_and_hash


class NotificationVerifier(_VerifierBase):
    """Verifies eBay push-notification signatures using an :class:`EbayClient`.

    Application credentials suffice (the public key is fetched with a client-credentials
    token on the base scope; a user-token client is scoped down automatically). ``verify``
    returns False for a bad or malformed signature — respond ``412``; it raises only on
    operational failures (key fetch, unsupported key type) — respond ``500`` and let eBay
    retry.
    """

    def __init__(self, client: EbayClient, *, cache_ttl: float = 3600.0) -> None:
        super().__init__(cache_ttl)
        self._client = _app_scoped(client)

    def verify(self, body: bytes, signature_header: str) -> bool:
        decoded = _decode_signature_header(signature_header)
        if decoded is None:
            return False
        kid, signature = decoded
        key_and_hash = self._cached(kid)
        if key_and_hash is None:
            key_and_hash = self._resolve(
                kid, self._client.commerce.notification.get_public_key(kid)
            )
        return _verify(key_and_hash, signature, body)


class AsyncNotificationVerifier(_VerifierBase):
    """Async counterpart of :class:`NotificationVerifier` for :class:`AsyncEbayClient`."""

    def __init__(self, client: AsyncEbayClient, *, cache_ttl: float = 3600.0) -> None:
        super().__init__(cache_ttl)
        self._client = _app_scoped(client)

    async def verify(self, body: bytes, signature_header: str) -> bool:
        decoded = _decode_signature_header(signature_header)
        if decoded is None:
            return False
        kid, signature = decoded
        key_and_hash = self._cached(kid)
        if key_and_hash is None:
            key_and_hash = self._resolve(
                kid, await self._client.commerce.notification.get_public_key(kid)
            )
        return _verify(key_and_hash, signature, body)
