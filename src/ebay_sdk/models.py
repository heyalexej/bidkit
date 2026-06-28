from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class EbayModel(BaseModel):
    """Base model for generated eBay schemas.

    eBay may add response fields without changing the OpenAPI document. Generated
    models therefore accept unknown response fields while still supporting JSON
    aliases such as ``itemId``.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="allow",
        populate_by_name=True,
        protected_namespaces=(),
    )
