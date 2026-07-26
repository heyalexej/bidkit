import httpx2
import pytest

from bidkit import EbayClient, EbayConfig


@pytest.fixture
def make_client():
    """Build an EbayClient over an httpx2.MockTransport handler."""

    def _make(handler, **config_kwargs) -> EbayClient:
        config_kwargs.setdefault("access_token", "token")
        return EbayClient(
            EbayConfig(**config_kwargs),
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        )

    return _make
