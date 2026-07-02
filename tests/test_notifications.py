import asyncio
import base64
import json

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from bidkit import (
    AsyncEbayClient,
    AsyncNotificationVerifier,
    EbayClient,
    EbayConfig,
    NotificationVerifier,
    challenge_response,
)

KID = "9936261a-7d7b-4621-a0f1-96ccb428af49"
BODY = (
    b'{"metadata":{"topic":"MARKETPLACE_ACCOUNT_DELETION"},'
    b'"notification":{"data":{"username":"x"}}}'
)


def _keypair() -> tuple[ec.EllipticCurvePrivateKey, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    # eBay serves the PEM with armor and body on one line.
    single_line = pem.replace("\n", "")
    return private_key, single_line


def _signature_header(private_key: ec.EllipticCurvePrivateKey, body: bytes) -> str:
    der = private_key.sign(body, ec.ECDSA(hashes.SHA1()))
    payload = {
        "alg": "ecdsa",
        "kid": KID,
        "signature": base64.b64encode(der).decode(),
        "digest": "SHA1",
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _handler(single_line_key: str, key_requests: dict[str, int]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "app-token", "expires_in": 7200})
        assert request.url.path == f"/commerce/notification/v1/public_key/{KID}"
        key_requests["n"] += 1
        return httpx.Response(
            200, json={"key": single_line_key, "algorithm": "ECDSA", "digest": "SHA1"}
        )

    return handler


def test_verify_accepts_valid_and_rejects_tampered_and_caches_the_key() -> None:
    private_key, single_line = _keypair()
    key_requests = {"n": 0}
    client = EbayClient(
        EbayConfig(app_id="app", cert_id="cert"),
        http_client=httpx.Client(
            transport=httpx.MockTransport(_handler(single_line, key_requests))
        ),
    )
    verifier = NotificationVerifier(client)
    header = _signature_header(private_key, BODY)

    assert verifier.verify(BODY, header) is True
    assert verifier.verify(BODY + b" ", header) is False  # tampered body
    assert verifier.verify(BODY, header) is True
    assert key_requests["n"] == 1  # key fetched once, then cached


def test_verify_rejects_malformed_headers_without_key_fetch() -> None:
    key_requests = {"n": 0}
    client = EbayClient(
        EbayConfig(app_id="app", cert_id="cert"),
        http_client=httpx.Client(transport=httpx.MockTransport(_handler("", key_requests))),
    )
    verifier = NotificationVerifier(client)

    assert verifier.verify(BODY, "not-base64!!") is False
    assert verifier.verify(BODY, base64.b64encode(b'{"no": "kid"}').decode()) is False
    assert key_requests["n"] == 0


def test_async_verifier_matches_sync_behavior() -> None:
    private_key, single_line = _keypair()
    key_requests = {"n": 0}

    async def run() -> None:
        client = AsyncEbayClient(
            EbayConfig(app_id="app", cert_id="cert"),
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(_handler(single_line, key_requests))
            ),
        )
        verifier = AsyncNotificationVerifier(client)
        header = _signature_header(private_key, BODY)
        try:
            assert await verifier.verify(BODY, header) is True
            assert await verifier.verify(b"tampered", header) is False
        finally:
            await client.close()

    asyncio.run(run())
    assert key_requests["n"] == 1


def test_challenge_response_matches_ebays_documented_computation() -> None:
    # sha256(challengeCode + verificationToken + endpoint), hex, in that exact order.
    result = challenge_response(
        "abc", "token_1234567890_abcdefghijklmnop", "https://example.com/hook"
    )

    import hashlib

    expected = hashlib.sha256(
        b"abc" + b"token_1234567890_abcdefghijklmnop" + b"https://example.com/hook"
    ).hexdigest()
    assert result == {"challengeResponse": expected}
