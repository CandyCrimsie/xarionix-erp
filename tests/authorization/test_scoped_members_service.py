import pytest

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.permissions.scopes import (
    PermissionScope,
)

from models.company import Company
from models.company_memberships import (
    CompanyMembership,
)
from models.membership_roles import (
    MembershipRole,
)
from models.organizational_units import (
    OrganizationalUnit,
    OrganizationalUnitType,
)
from models.permissions import Permission
from models.role_permissions import (
    RolePermission,
)
from models.roles import Role
from models.unit_memberships import (
    UnitMembership,
)
from models.users import User

from services.authorization import (
    clear_authorization_cache,
)

from services.company_memberships import (
    CompanyMembershipNotFoundError,
    CompanyMembershipPermissionDeniedError,
    get_scoped_company_membership,
    list_scoped_company_memberships,
)


async def create_membership(
    session: AsyncSession,
    *,
    company: Company,
    username: str,
) -> CompanyMembership:
    user = User(
        username=username,
        password_hash="test",
    )

    session.add(user)

    await session.flush()

    membership = CompanyMembership(
        user_id=user.id,
        company_id=company.id,
    )

    session.add(membership)

    await session.flush()

    return membership


async def create_role_with_members_read(
    session: AsyncSession,
    *,
    company: Company,
    membership: CompanyMembership,
    scope: PermissionScope,
) -> None:
    permission = Permission(
        code="members.read",
        name="Read members",
        module="members",
    )

    role = Role(
        company_id=company.id,
        name=f"Reader {scope.value}",
    )

    session.add_all(
        [
            permission,
            role,
        ]
    )

    await session.flush()

    session.add_all(
        [
            RolePermission(
                role_id=role.id,
                permission_id=permission.id,
                scope=scope,
            ),
            MembershipRole(
                company_membership_id=(
                    membership.id
                ),
                role_id=role.id,
            ),
        ]
    )

    await session.flush()


async def create_context(
    session: AsyncSession,
):
    company = Company(
        name="Main Company",
    )

    foreign_company = Company(
        name="Foreign Company",
    )

    session.add_all(
        [
            company,
            foreign_company,
        ]
    )

    await session.flush()

    support = OrganizationalUnit(
        company_id=company.id,
        name="Support",
        type=(
            OrganizationalUnitType.DEPARTMENT
        ),
    )

    support_l1 = OrganizationalUnit(
        company_id=company.id,
        name="Support L1",
        type=OrganizationalUnitType.TEAM,
    )

    noc = OrganizationalUnit(
        company_id=company.id,
        name="NOC",
        type=(
            OrganizationalUnitType.DEPARTMENT
        ),
    )

    session.add_all(
        [
            support,
            support_l1,
            noc,
        ]
    )

    await session.flush()

    support_l1.parent_id = support.id

    current = await create_membership(
        session,
        company=company,
        username="current-user",
    )

    same_unit = await create_membership(
        session,
        company=company,
        username="same-unit-user",
    )

    child_unit = await create_membership(
        session,
        company=company,
        username="child-unit-user",
    )

    other_unit = await create_membership(
        session,
        company=company,
        username="other-unit-user",
    )

    without_unit = await create_membership(
        session,
        company=company,
        username="without-unit-user",
    )

    foreign = await create_membership(
        session,
        company=foreign_company,
        username="foreign-user",
    )

    session.add_all(
        [
            UnitMembership(
                company_membership_id=(
                    current.id
                ),
                unit_id=support.id,
                is_primary=True,
            ),
            UnitMembership(
                company_membership_id=(
                    same_unit.id
                ),
                unit_id=support.id,
                is_primary=True,
            ),
            UnitMembership(
                company_membership_id=(
                    child_unit.id
                ),
                unit_id=support_l1.id,
                is_primary=True,
            ),
            UnitMembership(
                company_membership_id=(
                    other_unit.id
                ),
                unit_id=noc.id,
                is_primary=True,
            ),
        ]
    )

    await session.flush()

    return {
        "company": company,
        "foreign_company": foreign_company,

        "support": support,
        "support_l1": support_l1,
        "noc": noc,

        "current": current,
        "same_unit": same_unit,
        "child_unit": child_unit,
        "other_unit": other_unit,
        "without_unit": without_unit,
        "foreign": foreign,
    }


def membership_ids(
    memberships: list[CompanyMembership],
) -> set[int]:
    return {
        membership.id
        for membership in memberships
    }


@pytest.mark.asyncio
async def test_service_self_scope(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.SELF,
    )

    await db_session.commit()

    memberships = (
        await list_scoped_company_memberships(
            db_session,
            company_id=ctx["company"].id,
            current_membership_id=(
                ctx["current"].id
            ),
        )
    )

    assert membership_ids(
        memberships
    ) == {
        ctx["current"].id,
    }

    await clear_authorization_cache()


@pytest.mark.asyncio
async def test_service_own_unit_scope(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    memberships = (
        await list_scoped_company_memberships(
            db_session,
            company_id=ctx["company"].id,
            current_membership_id=(
                ctx["current"].id
            ),
        )
    )

    assert membership_ids(
        memberships
    ) == {
        ctx["current"].id,
        ctx["same_unit"].id,
    }

    await clear_authorization_cache()


@pytest.mark.asyncio
async def test_service_own_unit_tree_scope(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=(
            PermissionScope.OWN_UNIT_TREE
        ),
    )

    await db_session.commit()

    memberships = (
        await list_scoped_company_memberships(
            db_session,
            company_id=ctx["company"].id,
            current_membership_id=(
                ctx["current"].id
            ),
        )
    )

    assert membership_ids(
        memberships
    ) == {
        ctx["current"].id,
        ctx["same_unit"].id,
        ctx["child_unit"].id,
    }

    await clear_authorization_cache()


@pytest.mark.asyncio
async def test_service_company_scope(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    memberships = (
        await list_scoped_company_memberships(
            db_session,
            company_id=ctx["company"].id,
            current_membership_id=(
                ctx["current"].id
            ),
        )
    )

    assert membership_ids(
        memberships
    ) == {
        ctx["current"].id,
        ctx["same_unit"].id,
        ctx["child_unit"].id,
        ctx["other_unit"].id,
        ctx["without_unit"].id,
    }

    await clear_authorization_cache()


@pytest.mark.asyncio
async def test_service_without_permission_is_denied(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    with pytest.raises(
        CompanyMembershipPermissionDeniedError
    ):
        await list_scoped_company_memberships(
            db_session,
            company_id=ctx["company"].id,
            current_membership_id=(
                ctx["current"].id
            ),
        )

    await clear_authorization_cache()


@pytest.mark.asyncio
async def test_target_service_self_can_read_self(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.SELF,
    )

    await db_session.commit()

    membership = (
        await get_scoped_company_membership(
            db_session,
            company_id=ctx["company"].id,
            membership_id=ctx["current"].id,
            current_membership_id=(
                ctx["current"].id
            ),
        )
    )

    assert membership.id == ctx["current"].id

    await clear_authorization_cache()


@pytest.mark.asyncio
async def test_target_service_self_cannot_read_other(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.SELF,
    )

    await db_session.commit()

    with pytest.raises(
        CompanyMembershipNotFoundError
    ):
        await get_scoped_company_membership(
            db_session,
            company_id=ctx["company"].id,
            membership_id=(
                ctx["same_unit"].id
            ),
            current_membership_id=(
                ctx["current"].id
            ),
        )

    await clear_authorization_cache()


@pytest.mark.asyncio
async def test_target_service_own_unit_can_read_same_unit(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    membership = (
        await get_scoped_company_membership(
            db_session,
            company_id=ctx["company"].id,
            membership_id=(
                ctx["same_unit"].id
            ),
            current_membership_id=(
                ctx["current"].id
            ),
        )
    )

    assert membership.id == ctx["same_unit"].id

    await clear_authorization_cache()


@pytest.mark.asyncio
async def test_target_service_own_unit_cannot_read_child(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    with pytest.raises(
        CompanyMembershipNotFoundError
    ):
        await get_scoped_company_membership(
            db_session,
            company_id=ctx["company"].id,
            membership_id=(
                ctx["child_unit"].id
            ),
            current_membership_id=(
                ctx["current"].id
            ),
        )

    await clear_authorization_cache()


@pytest.mark.asyncio
async def test_target_service_own_unit_tree_can_read_child(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=(
            PermissionScope.OWN_UNIT_TREE
        ),
    )

    await db_session.commit()

    membership = (
        await get_scoped_company_membership(
            db_session,
            company_id=ctx["company"].id,
            membership_id=(
                ctx["child_unit"].id
            ),
            current_membership_id=(
                ctx["current"].id
            ),
        )
    )

    assert membership.id == ctx["child_unit"].id

    await clear_authorization_cache()


@pytest.mark.asyncio
async def test_target_service_own_unit_tree_cannot_read_other_branch(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=(
            PermissionScope.OWN_UNIT_TREE
        ),
    )

    await db_session.commit()

    with pytest.raises(
        CompanyMembershipNotFoundError
    ):
        await get_scoped_company_membership(
            db_session,
            company_id=ctx["company"].id,
            membership_id=(
                ctx["other_unit"].id
            ),
            current_membership_id=(
                ctx["current"].id
            ),
        )

    await clear_authorization_cache()


@pytest.mark.asyncio
async def test_target_service_company_can_read_company_member(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    membership = (
        await get_scoped_company_membership(
            db_session,
            company_id=ctx["company"].id,
            membership_id=(
                ctx["other_unit"].id
            ),
            current_membership_id=(
                ctx["current"].id
            ),
        )
    )

    assert membership.id == ctx["other_unit"].id

    await clear_authorization_cache()


@pytest.mark.asyncio
async def test_target_service_company_cannot_cross_company(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    with pytest.raises(
        CompanyMembershipNotFoundError
    ):
        await get_scoped_company_membership(
            db_session,
            company_id=ctx["company"].id,
            membership_id=ctx["foreign"].id,
            current_membership_id=(
                ctx["current"].id
            ),
        )

    await clear_authorization_cache()


@pytest.mark.asyncio
async def test_target_service_without_permission_is_denied(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    with pytest.raises(
        CompanyMembershipPermissionDeniedError
    ):
        await get_scoped_company_membership(
            db_session,
            company_id=ctx["company"].id,
            membership_id=ctx["current"].id,
            current_membership_id=(
                ctx["current"].id
            ),
        )

    await clear_authorization_cache()