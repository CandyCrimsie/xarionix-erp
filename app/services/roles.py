from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.roles import Role

from repositories.company import (
    get_company_by_id,
)

from repositories.roles import (
    create_role,
    get_company_roles,
    get_role_by_id,
    get_role_by_name,
)

from schemas.roles import (
    RoleCreate,
    RoleUpdate,
)

from services.authorization import (
    invalidate_role_permissions,
)


class CompanyNotFoundError(Exception):
    pass


class RoleNotFoundError(Exception):
    pass


class RoleAlreadyExistsError(Exception):
    pass


async def list_roles(
    session: AsyncSession,
    company_id: int,
) -> list[Role]:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    return await get_company_roles(
        session,
        company_id,
    )


async def create_new_role(
    session: AsyncSession,
    *,
    company_id: int,
    data: RoleCreate,
) -> Role:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    existing = await get_role_by_name(
        session,
        company_id=company_id,
        name=data.name,
    )

    if existing is not None:
        raise RoleAlreadyExistsError

    try:
        role = await create_role(
            session,
            company_id=company_id,
            name=data.name,
            description=data.description,
        )

        await session.commit()
        await session.refresh(role)

        return role

    except IntegrityError:
        await session.rollback()

        raise RoleAlreadyExistsError


async def get_role(
    session: AsyncSession,
    *,
    company_id: int,
    role_id: int,
) -> Role:
    role = await get_role_by_id(
        session,
        role_id,
    )

    if (
        role is None
        or role.company_id != company_id
    ):
        raise RoleNotFoundError

    return role


async def update_role(
    session: AsyncSession,
    *,
    company_id: int,
    role_id: int,
    data: RoleUpdate,
) -> Role:
    role = await get_role(
        session,
        company_id=company_id,
        role_id=role_id,
    )

    update_data = data.model_dump(
        exclude_unset=True,
    )

    if "name" in update_data:
        existing = await get_role_by_name(
            session,
            company_id=company_id,
            name=update_data["name"],
        )

        if (
            existing is not None
            and existing.id != role.id
        ):
            raise RoleAlreadyExistsError

    for field, value in update_data.items():
        setattr(
            role,
            field,
            value,
        )

    try:
        await session.commit()
        await session.refresh(role)

    except IntegrityError:
        await session.rollback()
        raise RoleAlreadyExistsError

    await invalidate_role_permissions(
        session,
        role_id=role.id,
    )

    return role