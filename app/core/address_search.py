import re
from dataclasses import dataclass


MAX_ADDRESS_SEARCH_TOKENS = 12
FUZZY_MIN_TOKEN_LENGTH = 5
FUZZY_SIMILARITY_THRESHOLD = 0.55


# These aliases describe query syntax only. They never change stored address
# values or the normalization used by uniqueness constraints.
ADDRESS_SEARCH_ABBREVIATIONS: dict[str, str] = {
    "г": "город",
    "город": "город",
    "ул": "улица",
    "улица": "улица",
    "пр": "проспект",
    "пр-т": "проспект",
    "просп": "проспект",
    "проспект": "проспект",
    "пер": "переулок",
    "переулок": "переулок",
    "обл": "область",
    "область": "область",
    "мкр": "микрорайон",
    "микрорайон": "микрорайон",
    "снт": "снт",
    "д": "дом",
    "дом": "дом",
    "корп": "корпус",
    "корпус": "корпус",
    "стр": "строение",
    "строение": "строение",
}


_ADDRESS_TYPE_WORDS = frozenset({
    "город",
    "улица",
    "проспект",
    "переулок",
    "область",
    "микрорайон",
    "снт",
})
_STRUCTURE_WORDS = frozenset({"дом", "корпус", "строение"})
_NUMERIC_NAME_FOLLOWERS = frozenset({
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
    "года", "лет",
})
_TOKEN_RE = re.compile(r"[0-9a-zа-я]+(?:[-/][0-9a-zа-я]+)*")
_HOUSE_NUMBER_RE = re.compile(
    r"^\d+[a-zа-я]?(?:[-/]\d+[a-zа-я]?)?$"
)
_COMPACT_PART_RE = re.compile(
    r"^(?P<marker>к|корп|корпус|стр|строение)"
    r"(?P<value>\d+[a-zа-я]?)$"
)


class AddressSearchQueryTooComplexError(ValueError):
    pass


@dataclass(slots=True, frozen=True)
class AddressSearchQuery:
    normalized: str
    name_tokens: tuple[str, ...]
    house_number: str | None = None
    corpus: str | None = None
    structure: str | None = None


def normalize_address_search_input(value: str) -> str:
    """Normalize user search syntax without changing stored address values."""
    normalized = value.casefold().replace("ё", "е")
    return " ".join(_TOKEN_RE.findall(normalized))


def parse_address_search_query(value: str) -> AddressSearchQuery:
    normalized = normalize_address_search_input(value)
    raw_tokens = normalized.split()
    if len(raw_tokens) > MAX_ADDRESS_SEARCH_TOKENS:
        raise AddressSearchQueryTooComplexError(
            f"Address search accepts at most {MAX_ADDRESS_SEARCH_TOKENS} tokens"
        )

    tokens = [ADDRESS_SEARCH_ABBREVIATIONS.get(token, token) for token in raw_tokens]
    has_standalone_number = any(_HOUSE_NUMBER_RE.fullmatch(token) for token in tokens)
    names: list[str] = []
    house_number: str | None = None
    corpus: str | None = None
    structure: str | None = None
    pending_part: str | None = None

    for index, token in enumerate(tokens):
        if token in _ADDRESS_TYPE_WORDS:
            continue
        if token in _STRUCTURE_WORDS:
            pending_part = token
            continue

        compact_part = _COMPACT_PART_RE.fullmatch(token)
        if compact_part and (house_number is not None or has_standalone_number):
            marker = compact_part.group("marker")
            value_part = compact_part.group("value")
            if marker in {"к", "корп", "корпус"}:
                corpus = value_part
            else:
                structure = value_part
            pending_part = None
            continue

        if pending_part is not None:
            if pending_part == "дом":
                house_number = token
            elif pending_part == "корпус":
                corpus = token
            else:
                structure = token
            pending_part = None
            continue

        if house_number is None and _HOUSE_NUMBER_RE.fullmatch(token):
            previous = tokens[index - 1] if index > 0 else None
            next_token = tokens[index + 1] if index + 1 < len(tokens) else None
            followed_by_name = next_token in _NUMERIC_NAME_FOLLOWERS
            # Digits are valid parts of geographic names (``8 Марта``,
            # ``1905 года`` and ``мкр. 1``). Explicit ``дом`` is already
            # handled above; an otherwise trailing number remains a house.
            if previous in _ADDRESS_TYPE_WORDS or followed_by_name:
                names.append(token)
            else:
                house_number = token
            continue

        names.append(token)

    # Repeated words do not add information and must not inflate relevance.
    unique_names = tuple(dict.fromkeys(names))
    return AddressSearchQuery(
        normalized=normalized,
        name_tokens=unique_names,
        house_number=house_number,
        corpus=corpus,
        structure=structure,
    )
