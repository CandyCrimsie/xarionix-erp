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


@pytest.mark.parametrize(
    ("query", "expected_names"),
    [
        ("ул. 8 Марта", ("8", "марта")),
        ("ул. 1905 года", ("1905", "года")),
        ("1-я улица", ("1-я",)),
        ("мкр. 1", ("1",)),
    ],
)
def test_parse_address_search_query_preserves_numbers_in_object_names(
    query: str,
    expected_names: tuple[str, ...],
):
    parsed = parse_address_search_query(query)

    assert parsed.name_tokens == expected_names
    assert parsed.house_number is None


def test_parse_address_search_query_limits_token_count():
    with pytest.raises(AddressSearchQueryTooComplexError):
        parse_address_search_query(" ".join(f"token{index}" for index in range(13)))
