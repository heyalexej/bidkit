from __future__ import annotations

from enum import StrEnum

import orjson

from bidkit.generated.models.commerce_identity import MarketplaceIdEnum
from bidkit.generated.models.sell_inventory import ConditionEnum, InventoryItem
from bidkit.models import OpenStrEnum


def test_generated_enums_are_open() -> None:
    # Still StrEnum-compatible (callers and existing checks rely on that)...
    assert issubclass(ConditionEnum, StrEnum)
    # ...but extend the open base.
    assert issubclass(ConditionEnum, OpenStrEnum)


def test_known_value_is_a_canonical_member() -> None:
    item = InventoryItem.model_validate({"condition": "NEW"})
    assert item.condition is ConditionEnum.new


def test_unknown_value_is_preserved_instead_of_raising() -> None:
    # A condition value eBay might add after our bundled spec snapshot.
    item = InventoryItem.model_validate({"condition": "LIKE_NEW_PREMIUM_2027"})
    assert isinstance(item.condition, ConditionEnum)
    # str() avoids the checker treating the enum as a closed literal set.
    assert str(item.condition) == "LIKE_NEW_PREMIUM_2027"


def test_unknown_value_round_trips_on_serialization() -> None:
    item = InventoryItem.model_validate({"condition": "LIKE_NEW_PREMIUM_2027"})
    payload = orjson.dumps(item.model_dump(by_alias=True, exclude_none=True)).decode()
    assert '"condition":"LIKE_NEW_PREMIUM_2027"' in payload


def test_unknown_values_do_not_pollute_the_known_member_set() -> None:
    before = set(MarketplaceIdEnum.__members__)
    MarketplaceIdEnum("EBAY_ATLANTIS")  # unknown
    assert set(MarketplaceIdEnum.__members__) == before
