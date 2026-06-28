"""eBay digital-signature (message signing) support.

Certain eBay APIs (notably the Finances API, plus several payout/refund operations in
EU/UK marketplaces) reject requests unless they carry an RFC 9421-style HTTP message
signature. eBay's variant signs a fixed list of components:

    "content-digest"        (only when the request has a body)
    "x-ebay-signature-key"  (the JWE that wraps the public signing key)
    "@method"
    "@path"
    "@authority"

The base string is signed with the seller's private key (Ed25519 by default, RSA
optional). This module is a faithful port of eBay's reference implementation
(https://github.com/ebay/digital-signature-nodejs-sdk).
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes

_BEGIN_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----"
_END_PRIVATE_KEY = "-----END PRIVATE KEY-----"

# eBay names the content-digest algorithm via the structured-field label, while the
# digest itself is computed with the matching hashlib constructor.
_DIGEST_LABELS = {"sha256": "sha-256", "sha512": "sha-512"}


def normalize_private_key_pem(private_key: str) -> str:
    """Accept a bare base64 PKCS#8 body or a full PEM block and return a PEM block."""
    key = private_key.strip()
    if key.startswith(_BEGIN_PRIVATE_KEY):
        return key
    return f"{_BEGIN_PRIVATE_KEY}\n{key}\n{_END_PRIVATE_KEY}"


def content_digest(body: bytes, digest: str = "sha256") -> str:
    """Return the ``Content-Digest`` header value for ``body``."""
    label = _DIGEST_LABELS.get(digest)
    if label is None:
        raise ValueError(f"Unsupported content digest: {digest!r} (use sha256 or sha512)")
    hashed = base64.b64encode(hashlib.new(digest, body).digest()).decode("ascii")
    return f"{label}=:{hashed}:"


def _signature_params(*, has_body: bool) -> list[str]:
    components = ["content-digest"] if has_body else []
    components += ["x-ebay-signature-key", "@method", "@path", "@authority"]
    return components


def _signature_params_value(*, has_body: bool) -> str:
    return " ".join(f'"{component}"' for component in _signature_params(has_body=has_body))


def signature_input(*, has_body: bool, created: int) -> str:
    return f"sig1=({_signature_params_value(has_body=has_body)});created={created}"


def base_string(
    *,
    method: str,
    authority: str,
    path: str,
    signature_key: str,
    digest_value: str | None,
    created: int,
) -> str:
    """Build the signature base string eBay expects (see module docstring)."""
    component_values = {
        "content-digest": digest_value,
        "x-ebay-signature-key": signature_key,
        "@method": method,
        "@path": path,
        "@authority": authority,
    }
    has_body = digest_value is not None
    lines = []
    for component in _signature_params(has_body=has_body):
        value = component_values[component]
        if value is None:
            raise ValueError(f"Missing value for signature component {component!r}")
        lines.append(f'"{component}": {value}')
    lines.append(
        f'"@signature-params": ({_signature_params_value(has_body=has_body)});created={created}'
    )
    return "\n".join(lines)


def _sign(private_key: PrivateKeyTypes, message: bytes) -> bytes:
    if isinstance(private_key, Ed25519PrivateKey):
        return private_key.sign(message)
    if isinstance(private_key, RSAPrivateKey):
        # eBay's RSA signing keys use RSASSA-PSS with SHA-256.
        return private_key.sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
    raise TypeError(
        f"Unsupported signing key type {type(private_key).__name__}; expected Ed25519 or RSA"
    )


class MessageSigner:
    """Holds a parsed private key + JWE and produces signed request headers."""

    def __init__(self, *, jwe: str, private_key_pem: str, digest: str = "sha256") -> None:
        self.jwe = jwe
        self.digest = digest
        self._private_key = serialization.load_pem_private_key(
            normalize_private_key_pem(private_key_pem).encode("utf-8"),
            password=None,
        )

    def headers(
        self,
        *,
        method: str,
        authority: str,
        path: str,
        body: bytes | None,
        created: int,
    ) -> dict[str, str]:
        """Return the full set of digital-signature headers for one request.

        ``authority`` is the host (no scheme), ``path`` is the request path without the
        query string, and ``body`` is the exact serialized request body (or ``None``/empty
        for bodyless requests).
        """
        digest_value = content_digest(body, self.digest) if body else None

        signed_headers: dict[str, str] = {
            "x-ebay-enforce-signature": "true",
            "x-ebay-signature-key": self.jwe,
        }
        if digest_value is not None:
            signed_headers["content-digest"] = digest_value
        signed_headers["signature-input"] = signature_input(
            has_body=digest_value is not None,
            created=created,
        )

        message = base_string(
            method=method.upper(),
            authority=authority,
            path=path,
            signature_key=self.jwe,
            digest_value=digest_value,
            created=created,
        )
        signature = base64.b64encode(_sign(self._private_key, message.encode("utf-8")))
        signed_headers["signature"] = f"sig1=:{signature.decode('ascii')}:"
        return signed_headers
