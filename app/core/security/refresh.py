import hashlib
import secrets
from uuid import UUID


class InvalidRefreshTokenError(Exception):
    pass


def generate_refresh_secret() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_secret(secret: str) -> str:
    return hashlib.sha256(
        secret.encode("utf-8")
    ).hexdigest()


def build_refresh_token(
    session_id: UUID,
    secret: str,
) -> str:
    return f"{session_id}.{secret}"


def parse_refresh_token(
    token: str,
) -> tuple[UUID, str]:
    session_id_raw, separator, secret = token.partition(".")

    if not separator or not secret:
        raise InvalidRefreshTokenError

    try:
        session_id = UUID(session_id_raw)
    except ValueError as exc:
        raise InvalidRefreshTokenError from exc

    return session_id, secret