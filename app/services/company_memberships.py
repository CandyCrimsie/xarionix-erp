from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.company import (
    Company,
)

from models.company_memberships import (
    CompanyMembership,
)

from repositories.company import (
    get_company_by_id,
)

from repositories.organizational_units import (
    get_organizational_unit_by_id,
)

from repositories.unit_memberships import (
    create_unit_membership,
)

from repositories.company_memberships import (
    create_company_membership,
    get_company_membership_by_id,
    get_company_membership_by_user,
    get_company_memberships,
    get_available_companies_for_user,
    get_scoped_company_membership_by_id,
    get_scoped_company_memberships,
)

from repositories.users import (
    get_user_by_id,
)

from core.permissions.codes import (
    PermissionCode,
)

from core.permissions.scopes import (
    PermissionScope,
)

from services.authorization import (
    AuthorizationService,
    invalidate_membership_permissions,
)

from services.scopes import (
    ScopeService,
)


class CompanyMembershipPermissionDeniedError(
    Exception
):
    pass


class CompanyNotFoundError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class CompanyMembershipNotFoundError(Exception):
    pass


class CompanyMembershipAlreadyExistsError(Exception):
    pass


class CompanyMembershipPrimaryUnitRequiredError(
    Exception
):
    pass


class CompanyMembershipUnitNotFoundError(
    Exception
):
    pass


async def list_scoped_company_memberships(
    session: AsyncSession,
    *,
    company_id: int,
    current_membership_id: int,
) -> list[CompanyMembership]:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    authorization = AuthorizationService(
        session
    )

    scope = await authorization.get_permission_scope(
        company_id=company_id,
        company_membership_id=(
            current_membership_id
        ),
        permission=PermissionCode.MEMBERS_READ,
    )

    if scope is None:
        raise (
            CompanyMembershipPermissionDeniedError
        )

    unit_ids: set[int] | None = None

    if scope in {
        PermissionScope.OWN_UNIT,
        PermissionScope.OWN_UNIT_TREE,
    }:
        scope_service = ScopeService(
            session
        )

        unit_ids = await scope_service.get_unit_ids(
            scope=scope,
            company_id=company_id,
            company_membership_id=(
                current_membership_id
            ),
        )

    return await get_scoped_company_memberships(
        session,
        company_id=company_id,
        current_membership_id=(
            current_membership_id
        ),
        scope=scope,
        unit_ids=unit_ids,
    )


async def list_company_memberships(
    session: AsyncSession,
    company_id: int,
) -> list[CompanyMembership]:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    return await get_company_memberships(
        session,
        company_id,
    )


async def add_user_to_company(
    session: AsyncSession,
    *,
    company_id: int,
    user_id: int,
) -> CompanyMembership:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    user = await get_user_by_id(
        session=session,
        user_id=user_id,
    )

    if user is None:
        raise UserNotFoundError

    existing_membership = (
        await get_company_membership_by_user(
            session,
            company_id=company_id,
            user_id=user_id,
        )
    )

    if existing_membership is not None:
        raise CompanyMembershipAlreadyExistsError

    try:
        membership = await create_company_membership(
            session,
            user_id=user_id,
            company_id=company_id,
        )

        await session.commit()
        await session.refresh(membership)

        return membership

    except IntegrityError:
        await session.rollback()

        raise CompanyMembershipAlreadyExistsError


async def add_scoped_user_to_company(
    session: AsyncSession,
    *,
    company_id: int,
    user_id: int,
    current_membership_id: int,
    primary_unit_id: int | None,
) -> CompanyMembership:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    user = await get_user_by_id(
        session=session,
        user_id=user_id,
    )

    if user is None:
        raise UserNotFoundError

    existing_membership = (
        await get_company_membership_by_user(
            session,
            company_id=company_id,
            user_id=user_id,
        )
    )

    if existing_membership is not None:
        raise CompanyMembershipAlreadyExistsError

    authorization = AuthorizationService(
        session
    )

    scope = await authorization.get_permission_scope(
        company_id=company_id,
        company_membership_id=(
            current_membership_id
        ),
        permission=PermissionCode.MEMBERS_MANAGE,
    )

    if scope is None:
        raise (
            CompanyMembershipPermissionDeniedError
        )

    #
    # Для unit-scoped manager нельзя создать
    # сотрудника без target unit, иначе scope
    # невозможно проверить.
    #
    if (
        scope
        in {
            PermissionScope.OWN_UNIT,
            PermissionScope.OWN_UNIT_TREE,
        }
        and primary_unit_id is None
    ):
        raise (
            CompanyMembershipPrimaryUnitRequiredError
        )

    if primary_unit_id is not None:
        unit = await get_organizational_unit_by_id(
            session,
            primary_unit_id,
        )

        if (
            unit is None
            or unit.company_id != company_id
            or not unit.is_active
        ):
            raise CompanyMembershipUnitNotFoundError

        if scope in {
            PermissionScope.OWN_UNIT,
            PermissionScope.OWN_UNIT_TREE,
        }:
            scope_service = ScopeService(
                session
            )

            allowed_unit_ids = (
                await scope_service.get_unit_ids(
                    scope=scope,
                    company_id=company_id,
                    company_membership_id=(
                        current_membership_id
                    ),
                )
            )

            if (
                primary_unit_id
                not in allowed_unit_ids
            ):
                raise (
                    CompanyMembershipUnitNotFoundError
                )

    try:
        membership = (
            await create_company_membership(
                session,
                user_id=user_id,
                company_id=company_id,
            )
        )

        if primary_unit_id is not None:
            await create_unit_membership(
                session,
                company_membership_id=(
                    membership.id
                ),
                unit_id=primary_unit_id,
                is_primary=True,
            )

        await session.commit()
        await session.refresh(
            membership
        )

        return membership

    except IntegrityError:
        await session.rollback()

        raise CompanyMembershipAlreadyExistsError


async def get_scoped_company_membership(
    session: AsyncSession,
    *,
    company_id: int,
    membership_id: int,
    current_membership_id: int,
) -> CompanyMembership:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    authorization = AuthorizationService(
        session
    )

    scope = await authorization.get_permission_scope(
        company_id=company_id,
        company_membership_id=(
            current_membership_id
        ),
        permission=PermissionCode.MEMBERS_READ,
    )

    if scope is None:
        raise (
            CompanyMembershipPermissionDeniedError
        )

    unit_ids: set[int] | None = None

    if scope in {
        PermissionScope.OWN_UNIT,
        PermissionScope.OWN_UNIT_TREE,
    }:
        scope_service = ScopeService(
            session
        )

        unit_ids = await scope_service.get_unit_ids(
            scope=scope,
            company_id=company_id,
            company_membership_id=(
                current_membership_id
            ),
        )

    membership = (
        await get_scoped_company_membership_by_id(
            session,
            company_id=company_id,
            membership_id=membership_id,
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


async def get_company_membership(
    session: AsyncSession,
    *,
    company_id: int,
    membership_id: int,
) -> CompanyMembership:
    membership = await get_company_membership_by_id(
        session,
        membership_id,
    )

    if (
        membership is None
        or membership.company_id != company_id
    ):
        raise CompanyMembershipNotFoundError

    return membership


async def update_scoped_company_membership(
    session: AsyncSession,
    *,
    company_id: int,
    membership_id: int,
    current_membership_id: int,
    is_active: bool,
) -> CompanyMembership:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    authorization = AuthorizationService(
        session
    )

    scope = await authorization.get_permission_scope(
        company_id=company_id,
        company_membership_id=(
            current_membership_id
        ),
        permission=PermissionCode.MEMBERS_MANAGE,
    )

    if scope is None:
        raise (
            CompanyMembershipPermissionDeniedError
        )

    unit_ids: set[int] | None = None

    if scope in {
        PermissionScope.OWN_UNIT,
        PermissionScope.OWN_UNIT_TREE,
    }:
        scope_service = ScopeService(
            session
        )

        unit_ids = await scope_service.get_unit_ids(
            scope=scope,
            company_id=company_id,
            company_membership_id=(
                current_membership_id
            ),
        )

    membership = (
        await get_scoped_company_membership_by_id(
            session,
            company_id=company_id,
            membership_id=membership_id,
            current_membership_id=(
                current_membership_id
            ),
            scope=scope,
            unit_ids=unit_ids,
        )
    )

    if membership is None:
        raise CompanyMembershipNotFoundError

    membership.is_active = is_active

    await session.commit()
    await session.refresh(
        membership
    )

    await invalidate_membership_permissions(
        company_id=membership.company_id,
        company_membership_id=membership.id,
    )

    return membership


async def update_company_membership(
    session: AsyncSession,
    *,
    company_id: int,
    membership_id: int,
    is_active: bool,
) -> CompanyMembership:
    membership = await get_company_membership(
        session,
        company_id=company_id,
        membership_id=membership_id,
    )

    membership.is_active = is_active

    await session.commit()
    await session.refresh(membership)

    await invalidate_membership_permissions(
        company_id=membership.company_id,
        company_membership_id=membership.id,
    )

    return membership


async def list_available_companies_for_user(
    session: AsyncSession,
    user_id: int,
) -> list[Company]:
    return await get_available_companies_for_user(
        session,
        user_id,
    )