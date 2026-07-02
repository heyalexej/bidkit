import httpx
import pytest

from bidkit import EbayClient, EbayConfig


@pytest.fixture
def make_client():
    """Build an EbayClient over an httpx.MockTransport handler."""

    def _make(handler, **config_kwargs) -> EbayClient:
        config_kwargs.setdefault("access_token", "token")
        return EbayClient(
            EbayConfig(**config_kwargs),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    return _make
