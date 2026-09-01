from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError

from core.config import config


@dataclass(slots=True, frozen=True)
class AccessTokenData:
    user_id: int
    session_id: UUID


class InvalidAccessTokenError(Exception):
    pass


def create_access_token(
    *,
    user_id: int,
    session_id: UUID,
) -> str:
    now = datetime.now(timezone.utc)

    expires_at = now + timedelta(
        minutes=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "type": "access",
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        config.JWT_SECRET,
        algorithm=config.JWT_ALGORITHM,
    )


def decode_access_token(
    token: str,
) -> AccessTokenData:
    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET,
            algorithms=[config.JWT_ALGORITHM],
        )

        if payload.get("type") != "access":
            raise InvalidAccessTokenError

        user_id = int(payload["sub"])
        session_id = UUID(payload["sid"])

    except (
        InvalidTokenError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise InvalidAccessTokenError from exc

    return AccessTokenData(
        user_id=user_id,
        session_id=session_id,
    )