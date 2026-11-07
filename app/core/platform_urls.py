"""Closed, operator-configured transport boundaries; never URLs from JWT/payload."""

from urllib.parse import urlsplit


def validate_platform_url(value: str, development: bool) -> None:
    parsed = urlsplit(value)
    _ = parsed.port  # Validate port syntax at configuration time.
    if (
        value != value.strip()
        or "\\" in value
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or value.endswith("/")
        or ".." in parsed.path.split("/")
        or (
            parsed.scheme != "https"
            and not (
                development
                and parsed.scheme == "http"
                and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            )
        )
    ):
        raise ValueError(
            "Platform URLs require HTTPS (explicit loopback development only)"
        )
