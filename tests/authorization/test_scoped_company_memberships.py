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
from models.organizational_units import (
    OrganizationalUnit,
    OrganizationalUnitType,
)
from models.unit_memberships import (
    UnitMembership,
)
from models.users import User

from repositories.company_memberships import (
    get_scoped_company_membership_by_id,
    get_scoped_company_memberships,
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
        type=(
            OrganizationalUnitType.TEAM
        ),
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
                company_membership_id=current.id,
                unit_id=support.id,
                is_primary=True,
            ),
            UnitMembership(
                company_membership_id=same_unit.id,
                unit_id=support.id,
                is_primary=True,
            ),
            UnitMembership(
                company_membership_id=child_unit.id,
                unit_id=support_l1.id,
                is_primary=True,
            ),
            UnitMembership(
                company_membership_id=other_unit.id,
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
async def test_self_scope_returns_only_current_membership(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    memberships = (
        await get_scoped_company_memberships(
            db_session,
            company_id=ctx["company"].id,
            current_membership_id=(
                ctx["current"].id
            ),
            scope=PermissionScope.SELF,
        )
    )

    assert membership_ids(
        memberships
    ) == {
        ctx["current"].id,
    }


@pytest.mark.asyncio
async def test_own_unit_returns_primary_unit_members(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    memberships = (
        await get_scoped_company_memberships(
            db_session,
            company_id=ctx["company"].id,
            current_membership_id=(
                ctx["current"].id
            ),
            scope=PermissionScope.OWN_UNIT,
            unit_ids={
                ctx["support"].id,
            },
        )
    )

    assert membership_ids(
        memberships
    ) == {
        ctx["current"].id,
        ctx["same_unit"].id,
    }


@pytest.mark.asyncio
async def test_own_unit_tree_returns_descendant_units(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    memberships = (
        await get_scoped_company_memberships(
            db_session,
            company_id=ctx["company"].id,
            current_membership_id=(
                ctx["current"].id
            ),
            scope=PermissionScope.OWN_UNIT_TREE,
            unit_ids={
                ctx["support"].id,
                ctx["support_l1"].id,
            },
        )
    )

    assert membership_ids(
        memberships
    ) == {
        ctx["current"].id,
        ctx["same_unit"].id,
        ctx["child_unit"].id,
    }


@pytest.mark.asyncio
async def test_company_scope_returns_entire_company_only(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    memberships = (
        await get_scoped_company_memberships(
            db_session,
            company_id=ctx["company"].id,
            current_membership_id=(
                ctx["current"].id
            ),
            scope=PermissionScope.COMPANY,
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


@pytest.mark.asyncio
async def test_unit_scope_without_units_returns_empty_list(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    memberships = (
        await get_scoped_company_memberships(
            db_session,
            company_id=ctx["company"].id,
            current_membership_id=(
                ctx["current"].id
            ),
            scope=PermissionScope.OWN_UNIT,
            unit_ids=set(),
        )
    )

    assert memberships == []


@pytest.mark.asyncio
async def test_target_self_scope_can_read_self(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    membership = (
        await get_scoped_company_membership_by_id(
            db_session,
            company_id=ctx["company"].id,
            membership_id=ctx["current"].id,
            current_membership_id=(
                ctx["current"].id
            ),
            scope=PermissionScope.SELF,
        )
    )

    assert membership is not None
    assert membership.id == ctx["current"].id


@pytest.mark.asyncio
async def test_target_self_scope_cannot_read_other_member(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    membership = (
        await get_scoped_company_membership_by_id(
            db_session,
            company_id=ctx["company"].id,
            membership_id=(
                ctx["same_unit"].id
            ),
            current_membership_id=(
                ctx["current"].id
            ),
            scope=PermissionScope.SELF,
        )
    )

    assert membership is None


@pytest.mark.asyncio
async def test_target_own_unit_can_read_same_unit(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    membership = (
        await get_scoped_company_membership_by_id(
            db_session,
            company_id=ctx["company"].id,
            membership_id=(
                ctx["same_unit"].id
            ),
            current_membership_id=(
                ctx["current"].id
            ),
            scope=PermissionScope.OWN_UNIT,
            unit_ids={
                ctx["support"].id,
            },
        )
    )

    assert membership is not None
    assert membership.id == ctx["same_unit"].id


@pytest.mark.asyncio
async def test_target_own_unit_cannot_read_child_unit(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    membership = (
        await get_scoped_company_membership_by_id(
            db_session,
            company_id=ctx["company"].id,
            membership_id=(
                ctx["child_unit"].id
            ),
            current_membership_id=(
                ctx["current"].id
            ),
            scope=PermissionScope.OWN_UNIT,
            unit_ids={
                ctx["support"].id,
            },
        )
    )

    assert membership is None


@pytest.mark.asyncio
async def test_target_own_unit_tree_can_read_child_unit(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    membership = (
        await get_scoped_company_membership_by_id(
            db_session,
            company_id=ctx["company"].id,
            membership_id=(
                ctx["child_unit"].id
            ),
            current_membership_id=(
                ctx["current"].id
            ),
            scope=(
                PermissionScope.OWN_UNIT_TREE
            ),
            unit_ids={
                ctx["support"].id,
                ctx["support_l1"].id,
            },
        )
    )

    assert membership is not None
    assert membership.id == ctx["child_unit"].id


@pytest.mark.asyncio
async def test_target_own_unit_tree_cannot_read_other_branch(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    membership = (
        await get_scoped_company_membership_by_id(
            db_session,
            company_id=ctx["company"].id,
            membership_id=(
                ctx["other_unit"].id
            ),
            current_membership_id=(
                ctx["current"].id
            ),
            scope=(
                PermissionScope.OWN_UNIT_TREE
            ),
            unit_ids={
                ctx["support"].id,
                ctx["support_l1"].id,
            },
        )
    )

    assert membership is None


@pytest.mark.asyncio
async def test_target_company_scope_can_read_company_member(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    membership = (
        await get_scoped_company_membership_by_id(
            db_session,
            company_id=ctx["company"].id,
            membership_id=(
                ctx["other_unit"].id
            ),
            current_membership_id=(
                ctx["current"].id
            ),
            scope=PermissionScope.COMPANY,
        )
    )

    assert membership is not None
    assert membership.id == ctx["other_unit"].id


@pytest.mark.asyncio
async def test_target_company_scope_cannot_cross_company(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    membership = (
        await get_scoped_company_membership_by_id(
            db_session,
            company_id=ctx["company"].id,
            membership_id=ctx["foreign"].id,
            current_membership_id=(
                ctx["current"].id
            ),
            scope=PermissionScope.COMPANY,
        )
    )

    assert membership is None


@pytest.mark.asyncio
async def test_target_unit_scope_without_units_returns_none(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    membership = (
        await get_scoped_company_membership_by_id(
            db_session,
            company_id=ctx["company"].id,
            membership_id=(
                ctx["same_unit"].id
            ),
            current_membership_id=(
                ctx["current"].id
            ),
            scope=PermissionScope.OWN_UNIT,
            unit_ids=set(),
        )
    )

    assert membership is None