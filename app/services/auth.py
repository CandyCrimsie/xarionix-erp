from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.security.password import hash_password, verify_password
from models.users import User
from repositories.users import (
    create_user,
    get_user_by_username,
)


class InvalidCredentialsError(Exception):
    pass


class UserDisabledError(Exception):
    pass


class UserAlreadyExistsError(Exception):
    pass


async def register_user(
    session: AsyncSession,
    *,
    username: str,
    password: str,
) -> User:
    existing_user = await get_user_by_username(
        session=session,
        username=username,
    )

    if existing_user is not None:
        raise UserAlreadyExistsError

    hashed_password = hash_password(password)

    try:
        user = await create_user(
            session=session,
            username=username,
            password_hash=hashed_password,
        )

        await session.commit()
        await session.refresh(user)

    except IntegrityError as exc:
        await session.rollback()

        raise UserAlreadyExistsError from exc

    return user


async def authenticate_user(
    session: AsyncSession,
    *,
    username: str,
    password: str,
) -> User:
    username = username.strip().lower()

    user = await get_user_by_username(
        session=session,
        username=username,
    )

    if user is None:
        raise InvalidCredentialsError

    if not verify_password(
        password,
        user.password_hash,
    ):
        raise InvalidCredentialsError

    if not user.is_active:
        raise UserDisabledError

    return user