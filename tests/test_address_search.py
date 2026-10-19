import pytest

from core.address_search import (
    AddressSearchQueryTooComplexError,
    normalize_address_search_input,
    parse_address_search_query,
)


@pytest.mark.parametrize(
    ("source", "normalized"),
    [
        ("  РАМ,   ГАГАР 53  ", "рам гагар 53"),
        (
            "г. Раменское, ул. Гагарина, д. 53",
            "г раменское ул гагарина д 53",
        ),
        ("Орёл, улица Ёлочная", "орел улица елочная"),
    ],
)
def test_normalize_address_search_input(source: str, normalized: str):
    assert normalize_address_search_input(source) == normalized


def test_parse_address_search_query_keeps_building_parts_separate():
    parsed = parse_address_search_query("Гагарина, 53 к2")

    assert parsed.name_tokens == ("гагарина",)
    assert parsed.house_number == "53"
    assert parsed.corpus == "2"
    assert parsed.structure is None

    structured = parse_address_search_query(
        "г. Раменское ул. Гагарина д. 53 корп. 2 стр. 4"
    )
    assert structured.name_tokens == ("раменское", "гагарина")
    assert structured.house_number == "53"
    assert structured.corpus == "2"
    assert structured.structure == "4"


def test_parse_address_search_query_limits_token_count():
    with pytest.raises(AddressSearchQueryTooComplexError):
        parse_address_search_query(" ".join(f"token{index}" for index in range(13)))
