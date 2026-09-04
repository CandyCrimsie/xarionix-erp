from sqlalchemy.ext.asyncio import AsyncSession

from models.company import Company
from repositories.company import (
    create_company,
    get_company_by_id,
    get_companies,
)
from schemas.company import (
    CompanyCreate,
    CompanyUpdate,
)


class CompanyNotFoundError(Exception):
    pass


class ParentCompanyNotFoundError(Exception):
    pass


class CompanyParentCycleError(Exception):
    pass


async def _validate_parent_change(
    *,
    session: AsyncSession,
    company_id: int,
    parent_id: int | None,
) -> None:
    if parent_id is None:
        return

    if parent_id == company_id:
        raise CompanyParentCycleError

    parent = await get_company_by_id(
        session,
        parent_id,
    )

    if parent is None:
        raise ParentCompanyNotFoundError

    current = parent

    while current.parent_id is not None:
        if current.parent_id == company_id:
            raise CompanyParentCycleError

        current = await get_company_by_id(
            session,
            current.parent_id,
        )

        if current is None:
            break


async def list_companies(
    session: AsyncSession,
) -> list[Company]:
    return await get_companies(session)


async def get_company(
    session: AsyncSession,
    company_id: int,
) -> Company:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    return company


async def create_new_company(
    session: AsyncSession,
    data: CompanyCreate,
) -> Company:
    if data.parent_id is not None:
        parent = await get_company_by_id(
            session,
            data.parent_id,
        )

        if parent is None:
            raise ParentCompanyNotFoundError

    company = await create_company(
        session,
        name=data.name,
        short_name=data.short_name,
        parent_id=data.parent_id,
    )

    await session.commit()
    await session.refresh(company)

    return company


async def update_company(
    session: AsyncSession,
    company_id: int,
    data: CompanyUpdate,
) -> Company:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    update_data = data.model_dump(
        exclude_unset=True,
    )

    if "parent_id" in update_data:
        parent_id = update_data["parent_id"]

        await _validate_parent_change(
            session=session,
            company_id=company.id,
            parent_id=parent_id,
        )

    for field, value in update_data.items():
        setattr(
            company,
            field,
            value,
        )

    await session.commit()
    await session.refresh(company)

    return company