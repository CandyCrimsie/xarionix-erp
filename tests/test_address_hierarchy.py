import pytest

from models.address_types import AddressType, AddressTypeCategory
from services.address_hierarchy import (
    InvalidAddressHierarchyTransitionError,
    _validate_transition,
    address_type_allows_buildings,
)
from services.address_types import address_type_code_base


def address_type(
    code: str,
    category: AddressTypeCategory,
) -> AddressType:
    return AddressType(
        code=code,
        category=category,
        name=code,
        short_name=None,
        sort_order=100,
        is_system=True,
    )


def test_city_accepts_area_territory_and_street_but_not_locality():
    city = address_type("city", AddressTypeCategory.LOCALITY)

    for child in (
        address_type("district", AddressTypeCategory.AREA),
        address_type("snt_territory", AddressTypeCategory.TERRITORY),
        address_type("street", AddressTypeCategory.THOROUGHFARE),
    ):
        _validate_transition(city, child)

    with pytest.raises(InvalidAddressHierarchyTransitionError):
        _validate_transition(
            city,
            address_type("settlement", AddressTypeCategory.LOCALITY),
        )


def test_only_thoroughfare_and_territory_categories_accept_buildings():
    assert address_type_allows_buildings(
        address_type("street", AddressTypeCategory.THOROUGHFARE)
    )
    assert address_type_allows_buildings(
        address_type("custom_snt", AddressTypeCategory.TERRITORY)
    )
    assert not address_type_allows_buildings(
        address_type("district", AddressTypeCategory.AREA)
    )


def test_custom_address_type_code_is_stable_and_ascii_safe():
    assert address_type_code_base(
        "  Гаражный кооператив  ",
        AddressTypeCategory.TERRITORY.value,
    ) == "custom_territory_garazhnyi_kooperativ"
