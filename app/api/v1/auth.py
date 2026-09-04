from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    Depends,
    status,
)

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from typing import Annotated

from dependencies.auth import get_current_user, CurrentAuth, get_current_auth
from dependencies.database import get_session

from schemas.user import UserCreate, UserResponse
from schemas.auth import LoginRequest, TokenResponse

from models.users import User

from services.auth import (
    UserAlreadyExistsError,
    InvalidCredentialsError,
    UserDisabledError,
    register_user,
    authenticate_user,
)
from services.sessions import (
    create_session,
    rotate_refresh_token,
    delete_session,
    delete_user_session,
    delete_all_user_sessions
)

from repositories.users import get_user_by_id

from core.config import config
from core.security.jwt import create_access_token
from core.security.cookies import set_refresh_cookie, delete_refresh_cookie


router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)


class InvalidRefreshTokenError(Exception):
    pass


class SessionNotFoundError(Exception):
    pass


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    data: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    try:
        user = await register_user(
            session=session,
            username=data.username,
            password=data.password,
        )

    except UserAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        )

    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    try:
        user = await authenticate_user(
            session=session,
            username=data.username,
            password=data.password,
        )

    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    except UserDisabledError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is disabled",
        )

    auth_session = await create_session(
        user_id=user.id,
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    access_token = create_access_token(
        user_id=user.id,
        session_id=auth_session.session_id,
    )

    set_refresh_cookie(
        response,
        auth_session.refresh_token,
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=(
            config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
            * 60
        ),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    refresh_token = request.cookies.get(
        config.REFRESH_COOKIE_NAME
    )

    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is missing",
        )

    try:
        auth_session = await rotate_refresh_token(
            refresh_token
        )

    except InvalidRefreshTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user = await get_user_by_id(
        session=session,
        user_id=auth_session.user_id,
    )

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is not available",
        )

    access_token = create_access_token(
        user_id=auth_session.user_id,
        session_id=auth_session.session_id,
    )

    set_refresh_cookie(
        response,
        auth_session.refresh_token,
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=(
            config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
            * 60
        ),
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
async def me(
    user: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    response: Response,
    auth: Annotated[
        CurrentAuth,
        Depends(get_current_auth),
    ],
) -> None:
    await delete_session(
        user_id=auth.user.id,
        session_id=auth.session_id,
    )

    delete_refresh_cookie(response)


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout_all(
    response: Response,
    auth: Annotated[
        CurrentAuth,
        Depends(get_current_auth),
    ],
) -> None:
    await delete_all_user_sessions(
        auth.user.id
    )

    delete_refresh_cookie(response)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_session(
    session_id: UUID,
    auth: Annotated[
        CurrentAuth,
        Depends(get_current_auth),
    ],
) -> None:
    try:
        await delete_user_session(
            user_id=auth.user.id,
            session_id=session_id,
        )

    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )