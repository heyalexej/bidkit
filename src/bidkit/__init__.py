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
from .notifications import (
    AsyncNotificationVerifier,
    NotificationVerifier,
    challenge_response,
)
from .pagination import paginate, paginate_async

try:
    __version__ = version("bidkit")
except PackageNotFoundError:  # running from a source tree without an installed dist
    __version__ = "0.1.2"

# Library logging convention: silent unless the application opts in, e.g.
#   logging.getLogger("bidkit").setLevel(logging.DEBUG)
logging.getLogger("bidkit").addHandler(logging.NullHandler())

__all__ = [
    "AsyncEbayClient",
    "AsyncNotificationVerifier",
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
    "NotificationVerifier",
    "OAuthTokens",
    "TokenCache",
    "challenge_response",
    "paginate",
    "paginate_async",
]
