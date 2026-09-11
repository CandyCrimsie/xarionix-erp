from sqlalchemy.ext.asyncio import AsyncSession

from models.organizational_units import (
    OrganizationalUnit,
)

from repositories.company import (
    get_company_by_id,
)

from repositories.organizational_units import (
    create_organizational_unit,
    get_company_organizational_units,
    get_organizational_unit_by_id,
    get_company_organizational_units_by_ids,
)

from schemas.organizational_units import (
    OrganizationalUnitCreate,
    OrganizationalUnitUpdate,
)

from core.permissions.codes import (
    PermissionCode,
)

from core.permissions.scopes import (
    PermissionScope,
)

from services.authorization import (
    AuthorizationService,
)

from services.scopes import (
    ScopeService,
)


class CompanyNotFoundError(Exception):
    pass


class OrganizationalUnitNotFoundError(Exception):
    pass


class ParentOrganizationalUnitNotFoundError(Exception):
    pass


class ParentOrganizationalUnitWrongCompanyError(
    Exception
):
    pass


class OrganizationalUnitHierarchyCycleError(
    Exception
):
    pass


class OrganizationalUnitPermissionDeniedError(
    Exception
):
    pass


async def _get_scoped_unit_ids(
    session: AsyncSession,
    *,
    company_id: int,
    current_membership_id: int,
    permission: PermissionCode,
) -> set[int] | None:
    authorization = AuthorizationService(
        session
    )

    scope = (
        await authorization
            .get_permission_scope(
                company_id=company_id,
                company_membership_id=(
                    current_membership_id
                ),
                permission=permission,
            )
    )

    if scope is None:
        raise (
            OrganizationalUnitPermissionDeniedError
        )


    if scope == PermissionScope.COMPANY:
        return None


    if scope in {
        PermissionScope.OWN_UNIT,
        PermissionScope.OWN_UNIT_TREE,
    }:
        scope_service = ScopeService(
            session
        )

        return await scope_service.get_unit_ids(
            scope=scope,
            company_id=company_id,
            company_membership_id=(
                current_membership_id
            ),
        )


    raise (
        OrganizationalUnitPermissionDeniedError
    )


async def _validate_parent_change(
    *,
    session: AsyncSession,
    unit: OrganizationalUnit,
    parent_id: int | None,
) -> None:
    if parent_id is None:
        return

    if parent_id == unit.id:
        raise OrganizationalUnitHierarchyCycleError

    parent = await get_organizational_unit_by_id(
        session,
        parent_id,
    )

    if parent is None:
        raise ParentOrganizationalUnitNotFoundError

    if parent.company_id != unit.company_id:
        raise ParentOrganizationalUnitWrongCompanyError

    visited: set[int] = set()

    current: OrganizationalUnit | None = parent

    while current is not None:
        if current.id == unit.id:
            raise OrganizationalUnitHierarchyCycleError

        if current.id in visited:
            raise OrganizationalUnitHierarchyCycleError

        visited.add(current.id)

        if current.parent_id is None:
            break

        current = await get_organizational_unit_by_id(
            session,
            current.parent_id,
        )


async def list_organizational_units(
    session: AsyncSession,
    company_id: int,
) -> list[OrganizationalUnit]:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    return await get_company_organizational_units(
        session,
        company_id,
    )


async def list_scoped_organizational_units(
    session: AsyncSession,
    *,
    company_id: int,
    current_membership_id: int,
) -> list[OrganizationalUnit]:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError


    unit_ids = await _get_scoped_unit_ids(
        session,
        company_id=company_id,
        current_membership_id=(
            current_membership_id
        ),
        permission=(
            PermissionCode
                .ORGANIZATIONAL_UNITS_READ
        ),
    )


    if unit_ids is None:
        return (
            await get_company_organizational_units(
                session,
                company_id,
            )
        )


    return (
        await get_company_organizational_units_by_ids(
            session,
            company_id=company_id,
            unit_ids=unit_ids,
        )
    )


async def create_new_organizational_unit(
    session: AsyncSession,
    company_id: int,
    data: OrganizationalUnitCreate,
) -> OrganizationalUnit:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    if data.parent_id is not None:
        parent = await get_organizational_unit_by_id(
            session,
            data.parent_id,
        )

        if parent is None:
            raise ParentOrganizationalUnitNotFoundError

        if parent.company_id != company_id:
            raise ParentOrganizationalUnitWrongCompanyError

    unit = await create_organizational_unit(
        session,
        company_id=company_id,
        parent_id=data.parent_id,
        name=data.name,
        type=data.type,
    )

    await session.commit()
    await session.refresh(unit)

    return unit


async def get_organizational_unit(
    session: AsyncSession,
    *,
    company_id: int,
    unit_id: int,
) -> OrganizationalUnit:
    unit = await get_organizational_unit_by_id(
        session,
        unit_id,
    )

    if (
        unit is None
        or unit.company_id != company_id
    ):
        raise OrganizationalUnitNotFoundError

    return unit


async def get_scoped_organizational_unit(
    session: AsyncSession,
    *,
    company_id: int,
    unit_id: int,
    current_membership_id: int,
) -> OrganizationalUnit:
    unit = await get_organizational_unit(
        session,
        company_id=company_id,
        unit_id=unit_id,
    )


    unit_ids = await _get_scoped_unit_ids(
        session,
        company_id=company_id,
        current_membership_id=(
            current_membership_id
        ),
        permission=(
            PermissionCode
                .ORGANIZATIONAL_UNITS_READ
        ),
    )


    if (
        unit_ids is not None
        and unit.id not in unit_ids
    ):
        raise (
            OrganizationalUnitNotFoundError
        )


    return unit


async def update_organizational_unit(
    session: AsyncSession,
    *,
    company_id: int,
    unit_id: int,
    data: OrganizationalUnitUpdate,
) -> OrganizationalUnit:
    unit = await get_organizational_unit(
        session,
        company_id=company_id,
        unit_id=unit_id,
    )

    update_data = data.model_dump(
        exclude_unset=True,
    )

    if "parent_id" in update_data:
        await _validate_parent_change(
            session=session,
            unit=unit,
            parent_id=update_data["parent_id"],
        )

    for field, value in update_data.items():
        setattr(
            unit,
            field,
            value,
        )

    await session.commit()
    await session.refresh(unit)

    return unit