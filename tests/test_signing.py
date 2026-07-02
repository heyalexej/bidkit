from __future__ import annotations

import base64
import hashlib

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bidkit import EbayClient, EbayConfig, EbaySigningConfig
from bidkit.signing import MessageSigner, base_string, content_digest, signature_input

JWE = "eyJ.fake.jwe"


def _ed25519_pem() -> tuple[str, Ed25519PrivateKey]:
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return pem, key


def test_content_digest_matches_structured_field_format() -> None:
    body = b'{"hello":"world"}'
    expected = base64.b64encode(hashlib.sha256(body).digest()).decode()
    assert content_digest(body, "sha256") == f"sha-256=:{expected}:"
    assert content_digest(body, "sha512").startswith("sha-512=:")


def test_base_string_omits_content_digest_for_bodyless_requests() -> None:
    bodyless = base_string(
        method="GET",
        authority="apiz.ebay.com",
        path="/sell/finances/v1/payout",
        signature_key=JWE,
        digest_value=None,
        created=1700000000,
    )
    assert "content-digest" not in bodyless
    assert bodyless.splitlines()[0] == f'"x-ebay-signature-key": {JWE}'
    assert bodyless.endswith(
        '"@signature-params": '
        '("x-ebay-signature-key" "@method" "@path" "@authority");created=1700000000'
    )

    signed = base_string(
        method="POST",
        authority="apiz.ebay.com",
        path="/sell/finances/v1/payout",
        signature_key=JWE,
        digest_value="sha-256=:abc:",
        created=1700000000,
    )
    assert signed.splitlines()[0] == '"content-digest": sha-256=:abc:'


def test_signature_input_lists_components_with_created() -> None:
    assert signature_input(has_body=False, created=42) == (
        'sig1=("x-ebay-signature-key" "@method" "@path" "@authority");created=42'
    )
    assert signature_input(has_body=True, created=42).startswith('sig1=("content-digest" ')


def test_signer_produces_a_verifiable_signature() -> None:
    pem, key = _ed25519_pem()
    signer = MessageSigner(jwe=JWE, private_key_pem=pem, digest="sha256")

    headers = signer.headers(
        method="post",
        authority="apiz.ebay.com",
        path="/sell/finances/v1/payout",
        body=b'{"amount":1}',
        created=1700000000,
    )

    assert headers["x-ebay-enforce-signature"] == "true"
    assert headers["x-ebay-signature-key"] == JWE
    assert headers["content-digest"] == content_digest(b'{"amount":1}', "sha256")

    expected_base = base_string(
        method="POST",
        authority="apiz.ebay.com",
        path="/sell/finances/v1/payout",
        signature_key=JWE,
        digest_value=headers["content-digest"],
        created=1700000000,
    )
    raw_signature = base64.b64decode(headers["signature"].removeprefix("sig1=:").removesuffix(":"))
    # Raises InvalidSignature if the base string / key do not match.
    key.public_key().verify(raw_signature, expected_base.encode())


def test_signer_accepts_bare_base64_private_key() -> None:
    pem, _ = _ed25519_pem()
    bare = "".join(line for line in pem.splitlines() if "PRIVATE KEY" not in line)
    # Should load without raising despite missing PEM armor.
    MessageSigner(jwe=JWE, private_key_pem=bare, digest="sha256")


def test_transport_signs_finances_requests_when_configured() -> None:
    pem, _ = _ed25519_pem()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"payouts": []})

    client = EbayClient(
        EbayConfig(
            access_token="token",
            marketplace_id="EBAY_DE",
            signing=EbaySigningConfig(jwe=JWE, private_key=pem),
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.sell.finances.get_payouts(raw_response=True)

    request = seen[0]
    assert request.url.host == "apiz.ebay.com"
    assert request.headers["x-ebay-enforce-signature"] == "true"
    assert request.headers["x-ebay-signature-key"] == JWE
    assert request.headers["signature"].startswith("sig1=:")
    # GET has no body, so no content-digest is emitted.
    assert "content-digest" not in request.headers
    assert request.headers["signature-input"].startswith(
        'sig1=("x-ebay-signature-key" "@method" "@path" "@authority")'
    )


def test_transport_skips_signing_when_unconfigured() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"payouts": []})

    client = EbayClient(
        EbayConfig(access_token="token", marketplace_id="EBAY_DE"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.sell.finances.get_payouts(raw_response=True)

    assert "signature" not in seen[0].headers
    assert "x-ebay-signature-key" not in seen[0].headers


def _signing_client(handler) -> EbayClient:
    pem, _ = _ed25519_pem()
    return EbayClient(
        EbayConfig(
            access_token="token",
            marketplace_id="EBAY_DE",
            signing=EbaySigningConfig(jwe=JWE, private_key=pem),
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_transport_does_not_sign_apis_that_do_not_require_it() -> None:
    """eBay rejects nothing without a signature outside the required set, so bidkit
    must not send x-ebay-enforce-signature on e.g. Browse calls (D10)."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = _signing_client(handler)
    client.buy.browse.get_item("v1|1|0", raw_response=True)
    client.sell.fulfillment.get_orders(raw_response=True)

    for request in seen:
        assert "signature" not in request.headers
        assert "x-ebay-enforce-signature" not in request.headers
        assert "x-ebay-signature-key" not in request.headers


def test_fulfillment_issue_refund_is_signed() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = _signing_client(handler)
    client.sell.fulfillment.issue_refund("11-11111-11111", raw_response=True)

    request = seen[0]
    assert request.method == "POST"
    assert request.headers["x-ebay-enforce-signature"] == "true"
    assert request.headers["signature"].startswith("sig1=:")


def test_post_order_issue_case_refund_is_signed() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = _signing_client(handler)
    client.post_order.case.issue_case_refund("5000000000", raw_response=True)

    request = seen[0]
    assert request.url.path == "/post-order/v2/casemanagement/5000000000/issue_refund"
    assert request.headers["x-ebay-enforce-signature"] == "true"
    assert request.headers["signature"].startswith("sig1=:")


def test_sign_all_escape_hatch_signs_everything() -> None:
    pem, _ = _ed25519_pem()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = EbayClient(
        EbayConfig(
            access_token="token",
            signing=EbaySigningConfig(jwe=JWE, private_key=pem, sign_all=True),
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.buy.browse.get_item("v1|1|0", raw_response=True)

    assert seen[0].headers["x-ebay-enforce-signature"] == "true"
    assert seen[0].headers["signature"].startswith("sig1=:")
