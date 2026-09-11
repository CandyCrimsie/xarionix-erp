from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.unit_memberships import UnitMembership
from models.company_memberships import (
    CompanyMembership,
)

from repositories.company_memberships import (
    get_company_membership_by_id,
    get_scoped_company_membership_by_id,
)

from repositories.organizational_units import (
    get_organizational_unit_by_id,
)

from repositories.unit_memberships import (
    clear_primary_unit_memberships,
    create_unit_membership,
    get_membership_units,
    get_unit_membership,
    get_unit_membership_by_id,
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


class CompanyMembershipNotFoundError(Exception):
    pass


class OrganizationalUnitNotFoundError(Exception):
    pass


class OrganizationalUnitWrongCompanyError(Exception):
    pass


class UnitMembershipNotFoundError(Exception):
    pass


class UnitMembershipAlreadyExistsError(Exception):
    pass

class UnitMembershipPermissionDeniedError(
    Exception
):
    pass


async def _get_scoped_company_membership(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
    current_membership_id: int,
    permission: PermissionCode,
) -> CompanyMembership:
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
            UnitMembershipPermissionDeniedError
        )


    unit_ids: set[int] | None = None

    if scope in {
        PermissionScope.OWN_UNIT,
        PermissionScope.OWN_UNIT_TREE,
    }:
        scope_service = ScopeService(
            session
        )

        unit_ids = (
            await scope_service
                .get_unit_ids(
                    scope=scope,
                    company_id=company_id,
                    company_membership_id=(
                        current_membership_id
                    ),
                )
        )


    membership = (
        await get_scoped_company_membership_by_id(
            session,
            company_id=company_id,
            membership_id=(
                company_membership_id
            ),
            current_membership_id=(
                current_membership_id
            ),
            scope=scope,
            unit_ids=unit_ids,
        )
    )

    if membership is None:
        raise CompanyMembershipNotFoundError


    return membership


async def list_membership_units(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
) -> list[UnitMembership]:
    await _get_company_membership(
        session,
        company_id=company_id,
        company_membership_id=company_membership_id,
    )

    return await get_membership_units(
        session,
        company_membership_id,
    )


async def list_scoped_membership_units(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
    current_membership_id: int,
) -> list[UnitMembership]:
    await _get_scoped_company_membership(
        session,
        company_id=company_id,
        company_membership_id=(
            company_membership_id
        ),
        current_membership_id=(
            current_membership_id
        ),
        permission=(
            PermissionCode.MEMBERS_READ
        ),
    )

    return await get_membership_units(
        session,
        company_membership_id,
    )


async def add_membership_to_unit(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
    unit_id: int,
    is_primary: bool,
) -> UnitMembership:
    company_membership = await _get_company_membership(
        session,
        company_id=company_id,
        company_membership_id=company_membership_id,
    )

    unit = await get_organizational_unit_by_id(
        session,
        unit_id,
    )

    if unit is None:
        raise OrganizationalUnitNotFoundError

    if unit.company_id != company_membership.company_id:
        raise OrganizationalUnitWrongCompanyError

    existing = await get_unit_membership(
        session,
        company_membership_id=company_membership_id,
        unit_id=unit_id,
    )

    if existing is not None:
        raise UnitMembershipAlreadyExistsError

    try:
        if is_primary:
            await clear_primary_unit_memberships(
                session,
                company_membership_id,
            )

        unit_membership = await create_unit_membership(
            session,
            company_membership_id=company_membership_id,
            unit_id=unit_id,
            is_primary=is_primary,
        )

        await session.commit()
        await session.refresh(unit_membership)

        return unit_membership

    except IntegrityError:
        await session.rollback()

        raise UnitMembershipAlreadyExistsError


async def get_membership_unit(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
    unit_membership_id: int,
) -> UnitMembership:
    await _get_company_membership(
        session,
        company_id=company_id,
        company_membership_id=company_membership_id,
    )

    unit_membership = await get_unit_membership_by_id(
        session,
        unit_membership_id,
    )

    if (
        unit_membership is None
        or unit_membership.company_membership_id
        != company_membership_id
    ):
        raise UnitMembershipNotFoundError

    return unit_membership


async def get_scoped_membership_unit(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
    unit_membership_id: int,
    current_membership_id: int,
) -> UnitMembership:
    await _get_scoped_company_membership(
        session,
        company_id=company_id,
        company_membership_id=(
            company_membership_id
        ),
        current_membership_id=(
            current_membership_id
        ),
        permission=(
            PermissionCode.MEMBERS_READ
        ),
    )


    unit_membership = (
        await get_unit_membership_by_id(
            session,
            unit_membership_id,
        )
    )

    if (
        unit_membership is None
        or unit_membership
            .company_membership_id
        != company_membership_id
    ):
        raise UnitMembershipNotFoundError


    return unit_membership


async def update_membership_unit(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
    unit_membership_id: int,
    is_primary: bool | None,
    is_active: bool | None,
) -> UnitMembership:
    unit_membership = await get_membership_unit(
        session,
        company_id=company_id,
        company_membership_id=company_membership_id,
        unit_membership_id=unit_membership_id,
    )

    if is_primary is True:
        await clear_primary_unit_memberships(
            session,
            company_membership_id,
        )

        unit_membership.is_primary = True

    elif is_primary is False:
        unit_membership.is_primary = False

    if is_active is False:
        unit_membership.is_active = False
        unit_membership.is_primary = False

    elif is_active is True:
        unit_membership.is_active = True

    await session.commit()
    await session.refresh(unit_membership)

    return unit_membership


async def _get_company_membership(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
):
    membership = await get_company_membership_by_id(
        session,
        company_membership_id,
    )

    if (
        membership is None
        or membership.company_id != company_id
    ):
        raise CompanyMembershipNotFoundError

    return membership