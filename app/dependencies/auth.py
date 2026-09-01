from typing import Annotated
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.ext.asyncio import AsyncSession

from core.security.jwt import (
    InvalidAccessTokenError,
    decode_access_token,
)
from dependencies.database import get_session

from models.users import User

from repositories.users import get_user_by_id

from services.sessions import get_auth_session


@dataclass(slots=True, frozen=True)
class CurrentAuth:
    user: User
    session_id: UUID


bearer_scheme = HTTPBearer(
    auto_error=False,
)


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )


async def get_current_auth(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> CurrentAuth:
    if credentials is None:
        raise unauthorized()

    try:
        token_data = decode_access_token(
            credentials.credentials
        )

    except InvalidAccessTokenError:
        raise unauthorized()

    auth_session = await get_auth_session(
        token_data.session_id
    )

    if auth_session is None:
        raise unauthorized()

    if auth_session.user_id != token_data.user_id:
        raise unauthorized()

    user = await get_user_by_id(
        session=session,
        user_id=token_data.user_id,
    )

    if user is None:
        raise unauthorized()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is disabled",
        )

    return CurrentAuth(
        user=user,
        session_id=token_data.session_id,
    )


async def get_current_user(
    auth: Annotated[
        CurrentAuth,
        Depends(get_current_auth),
    ],
) -> User:
    return auth.user