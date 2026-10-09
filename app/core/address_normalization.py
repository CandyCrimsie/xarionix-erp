import re


_WHITESPACE_RE = re.compile(r"\s+")


def clean_address_value(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.strip())


def normalize_address_value(value: str) -> str:
    return clean_address_value(value).casefold()


def clean_optional_address_value(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = clean_address_value(value)
    return cleaned or None
