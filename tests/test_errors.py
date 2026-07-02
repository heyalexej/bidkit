import httpx

from bidkit.errors import EbayAPIError


def _response(
    status: int,
    *,
    json_body: dict | None = None,
    text: str | None = None,
    headers: dict | None = None,
) -> httpx.Response:
    request = httpx.Request("GET", "https://api.ebay.com/x")
    if json_body is not None:
        return httpx.Response(status, json=json_body, headers=headers, request=request)
    return httpx.Response(status, text=text or "", headers=headers, request=request)


def test_message_comes_from_first_ebay_error_entry() -> None:
    error = EbayAPIError.from_response(
        _response(
            400,
            json_body={
                "errors": [
                    {"errorId": 25001, "message": "Invalid SKU.", "longMessage": "The SKU is bad."},
                    {"errorId": 25002, "message": "Second error"},
                ]
            },
        )
    )

    assert str(error) == "Invalid SKU."
    assert error.status_code == 400
    assert error.payload["errors"][0]["errorId"] == 25001


def test_message_falls_back_to_long_message_then_oauth_and_plain_shapes() -> None:
    long_only = EbayAPIError.from_response(
        _response(400, json_body={"errors": [{"longMessage": "Only long."}]})
    )
    oauth = EbayAPIError.from_response(
        _response(
            401, json_body={"error": "invalid_grant", "error_description": "Bad refresh token"}
        )
    )
    plain = EbayAPIError.from_response(_response(403, json_body={"message": "Forbidden by policy"}))

    assert str(long_only) == "Only long."
    assert str(oauth) == "Bad refresh token"
    assert str(plain) == "Forbidden by policy"


def test_non_json_body_keeps_reason_phrase_and_text_payload() -> None:
    error = EbayAPIError.from_response(_response(502, text="<html>Bad Gateway</html>"))

    assert error.status_code == 502
    assert error.payload == "<html>Bad Gateway</html>"
    assert "Bad Gateway" in str(error)


def test_request_id_is_read_from_ebay_headers() -> None:
    primary = EbayAPIError.from_response(
        _response(500, json_body={}, headers={"x-ebay-c-request-id": "rid-1"})
    )
    fallback = EbayAPIError.from_response(
        _response(500, json_body={}, headers={"x-ebay-request-id": "rid-2"})
    )
    absent = EbayAPIError.from_response(_response(500, json_body={}))

    assert primary.request_id == "rid-1"
    assert fallback.request_id == "rid-2"
    assert absent.request_id is None
