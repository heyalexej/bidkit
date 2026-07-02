import logging
from importlib.metadata import PackageNotFoundError, version

from .auth import FileTokenCache, InMemoryTokenCache, OAuthTokens, TokenCache
from .client import AsyncEbayClient, EbayClient
from .config import EbayConfig, EbaySigningConfig
from .errors import (
    EbayAPIError,
    EbayAuthError,
    EbayConfigError,
    EbaySDKError,
    EbayTransportError,
)
from .pagination import paginate, paginate_async

try:
    __version__ = version("bidkit")
except PackageNotFoundError:  # running from a source tree without an installed dist
    __version__ = "0.0.0"

# Library logging convention: silent unless the application opts in, e.g.
#   logging.getLogger("bidkit").setLevel(logging.DEBUG)
logging.getLogger("bidkit").addHandler(logging.NullHandler())

__all__ = [
    "AsyncEbayClient",
    "EbayAPIError",
    "EbayAuthError",
    "EbayClient",
    "EbayConfig",
    "EbayConfigError",
    "EbaySDKError",
    "EbaySigningConfig",
    "EbayTransportError",
    "FileTokenCache",
    "InMemoryTokenCache",
    "OAuthTokens",
    "TokenCache",
    "paginate",
    "paginate_async",
]
