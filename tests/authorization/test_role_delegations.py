import pytest

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from models.company import Company
from models.roles import Role

from services.role_delegations import (
    InvalidAssignableRolesError,
    RoleInactiveError,
    RoleNotFoundError,
    list_role_delegations,
    replace_role_delegations_for_role,
)


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

    manager = Role(
        company_id=company.id,
        name="Support Manager",
    )

    operator = Role(
        company_id=company.id,
        name="Support Operator",
    )

    trainee = Role(
        company_id=company.id,
        name="Support Trainee",
    )

    viewer = Role(
        company_id=company.id,
        name="Support Viewer",
    )

    inactive = Role(
        company_id=company.id,
        name="Inactive Role",
        is_active=False,
    )

    foreign = Role(
        company_id=foreign_company.id,
        name="Foreign Role",
    )

    session.add_all(
        [
            manager,
            operator,
            trainee,
            viewer,
            inactive,
            foreign,
        ]
    )

    await session.flush()

    return {
        "company": company,
        "foreign_company": foreign_company,

        "manager": manager,
        "operator": operator,
        "trainee": trainee,
        "viewer": viewer,
        "inactive": inactive,
        "foreign": foreign,
    }


def assignable_role_ids(
    delegations,
) -> set[int]:
    return {
        delegation.assignable_role_id
        for delegation in delegations
    }


@pytest.mark.asyncio
async def test_replace_role_delegations(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    delegations = (
        await replace_role_delegations_for_role(
            db_session,
            company_id=ctx["company"].id,
            manager_role_id=(
                ctx["manager"].id
            ),
            assignable_role_ids=[
                ctx["operator"].id,
                ctx["trainee"].id,
            ],
        )
    )

    assert assignable_role_ids(
        delegations
    ) == {
        ctx["operator"].id,
        ctx["trainee"].id,
    }


@pytest.mark.asyncio
async def test_list_role_delegations(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    await replace_role_delegations_for_role(
        db_session,
        company_id=ctx["company"].id,
        manager_role_id=ctx["manager"].id,
        assignable_role_ids=[
            ctx["operator"].id,
            ctx["viewer"].id,
        ],
    )

    delegations = await list_role_delegations(
        db_session,
        company_id=ctx["company"].id,
        manager_role_id=ctx["manager"].id,
    )

    assert assignable_role_ids(
        delegations
    ) == {
        ctx["operator"].id,
        ctx["viewer"].id,
    }


@pytest.mark.asyncio
async def test_foreign_manager_role_is_not_found(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    with pytest.raises(
        RoleNotFoundError
    ):
        await replace_role_delegations_for_role(
            db_session,
            company_id=ctx["company"].id,
            manager_role_id=ctx["foreign"].id,
            assignable_role_ids=[],
        )


@pytest.mark.asyncio
async def test_missing_manager_role_is_not_found(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    with pytest.raises(
        RoleNotFoundError
    ):
        await replace_role_delegations_for_role(
            db_session,
            company_id=ctx["company"].id,
            manager_role_id=999999999,
            assignable_role_ids=[],
        )


@pytest.mark.asyncio
async def test_inactive_manager_role_is_rejected(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    ctx["manager"].is_active = False

    await db_session.commit()

    with pytest.raises(
        RoleInactiveError
    ):
        await replace_role_delegations_for_role(
            db_session,
            company_id=ctx["company"].id,
            manager_role_id=(
                ctx["manager"].id
            ),
            assignable_role_ids=[
                ctx["operator"].id,
            ],
        )


@pytest.mark.asyncio
async def test_foreign_assignable_role_is_invalid(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    with pytest.raises(
        InvalidAssignableRolesError
    ) as exc_info:
        await replace_role_delegations_for_role(
            db_session,
            company_id=ctx["company"].id,
            manager_role_id=(
                ctx["manager"].id
            ),
            assignable_role_ids=[
                ctx["operator"].id,
                ctx["foreign"].id,
            ],
        )

    assert exc_info.value.role_ids == [
        ctx["foreign"].id,
    ]


@pytest.mark.asyncio
async def test_inactive_assignable_role_is_invalid(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    with pytest.raises(
        InvalidAssignableRolesError
    ) as exc_info:
        await replace_role_delegations_for_role(
            db_session,
            company_id=ctx["company"].id,
            manager_role_id=(
                ctx["manager"].id
            ),
            assignable_role_ids=[
                ctx["inactive"].id,
            ],
        )

    assert exc_info.value.role_ids == [
        ctx["inactive"].id,
    ]


@pytest.mark.asyncio
async def test_missing_assignable_role_is_invalid(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    missing_role_id = 999999999

    with pytest.raises(
        InvalidAssignableRolesError
    ) as exc_info:
        await replace_role_delegations_for_role(
            db_session,
            company_id=ctx["company"].id,
            manager_role_id=(
                ctx["manager"].id
            ),
            assignable_role_ids=[
                ctx["operator"].id,
                missing_role_id,
            ],
        )

    assert exc_info.value.role_ids == [
        missing_role_id,
    ]


@pytest.mark.asyncio
async def test_duplicate_assignable_role_ids_are_deduplicated(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    delegations = (
        await replace_role_delegations_for_role(
            db_session,
            company_id=ctx["company"].id,
            manager_role_id=(
                ctx["manager"].id
            ),
            assignable_role_ids=[
                ctx["operator"].id,
                ctx["trainee"].id,
                ctx["operator"].id,
                ctx["trainee"].id,
            ],
        )
    )

    assert assignable_role_ids(
        delegations
    ) == {
        ctx["operator"].id,
        ctx["trainee"].id,
    }

    assert len(delegations) == 2


@pytest.mark.asyncio
async def test_replace_removes_old_delegations(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    await replace_role_delegations_for_role(
        db_session,
        company_id=ctx["company"].id,
        manager_role_id=ctx["manager"].id,
        assignable_role_ids=[
            ctx["operator"].id,
            ctx["trainee"].id,
            ctx["viewer"].id,
        ],
    )

    delegations = (
        await replace_role_delegations_for_role(
            db_session,
            company_id=ctx["company"].id,
            manager_role_id=(
                ctx["manager"].id
            ),
            assignable_role_ids=[
                ctx["operator"].id,
                ctx["viewer"].id,
            ],
        )
    )

    assert assignable_role_ids(
        delegations
    ) == {
        ctx["operator"].id,
        ctx["viewer"].id,
    }

    assert ctx["trainee"].id not in (
        assignable_role_ids(
            delegations
        )
    )


@pytest.mark.asyncio
async def test_empty_list_clears_role_delegations(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    await replace_role_delegations_for_role(
        db_session,
        company_id=ctx["company"].id,
        manager_role_id=ctx["manager"].id,
        assignable_role_ids=[
            ctx["operator"].id,
            ctx["trainee"].id,
        ],
    )

    delegations = (
        await replace_role_delegations_for_role(
            db_session,
            company_id=ctx["company"].id,
            manager_role_id=(
                ctx["manager"].id
            ),
            assignable_role_ids=[],
        )
    )

    assert delegations == []


@pytest.mark.asyncio
async def test_invalid_replace_keeps_existing_delegations(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    await replace_role_delegations_for_role(
        db_session,
        company_id=ctx["company"].id,
        manager_role_id=ctx["manager"].id,
        assignable_role_ids=[
            ctx["operator"].id,
            ctx["trainee"].id,
        ],
    )

    with pytest.raises(
        InvalidAssignableRolesError
    ):
        await replace_role_delegations_for_role(
            db_session,
            company_id=ctx["company"].id,
            manager_role_id=(
                ctx["manager"].id
            ),
            assignable_role_ids=[
                ctx["viewer"].id,
                ctx["foreign"].id,
            ],
        )

    delegations = await list_role_delegations(
        db_session,
        company_id=ctx["company"].id,
        manager_role_id=ctx["manager"].id,
    )

    assert assignable_role_ids(
        delegations
    ) == {
        ctx["operator"].id,
        ctx["trainee"].id,
    }