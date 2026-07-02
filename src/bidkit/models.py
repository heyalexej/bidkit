from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class OpenStrEnum(StrEnum):
    """A string enum that tolerates values it does not know about.

    eBay adds enum members over time (new marketplaces, currencies, item conditions, ...) and
    the bundled OpenAPI specs are a snapshot. A plain ``StrEnum`` would raise ``ValidationError``
    on an unseen value and fail the whole response. This base preserves unknown values as
    transient members instead, so ``item.condition == "SOME_NEW_CONDITION"`` still works while
    known values remain canonical members (``is ConditionEnum.new`` holds).
    """

    @classmethod
    def _missing_(cls, value: object) -> Any:
        if not isinstance(value, str):
            return None
        member: Any = str.__new__(cls, value)
        member._name_ = value
        member._value_ = value
        return member


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
        defer_build=True,
    )
