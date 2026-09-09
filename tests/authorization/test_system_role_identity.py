import pytest

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.system_roles import (
    SystemRoleKey,
)

from models.company import Company
from models.roles import Role

from repositories.roles import (
    get_system_role_by_key,
)


async def create_company(
    session: AsyncSession,
    *,
    name: str,
) -> Company:
    company = Company(
        name=name,
    )

    session.add(
        company
    )

    await session.flush()

    return company


@pytest.mark.asyncio
async def test_system_role_requires_system_key(
    db_session: AsyncSession,
):
    company = await create_company(
        db_session,
        name="Main Company",
    )

    db_session.add(
        Role(
            company_id=company.id,
            name="Administrator",
            is_system=True,
            system_key=None,
        )
    )

    with pytest.raises(
        IntegrityError
    ):
        await db_session.flush()


@pytest.mark.asyncio
async def test_non_system_role_cannot_have_system_key(
    db_session: AsyncSession,
):
    company = await create_company(
        db_session,
        name="Main Company",
    )

    db_session.add(
        Role(
            company_id=company.id,
            name="Custom Role",
            is_system=False,
            system_key=(
                SystemRoleKey.ADMINISTRATOR.value
            ),
        )
    )

    with pytest.raises(
        IntegrityError
    ):
        await db_session.flush()


@pytest.mark.asyncio
async def test_company_cannot_have_duplicate_system_role_key(
    db_session: AsyncSession,
):
    company = await create_company(
        db_session,
        name="Main Company",
    )

    db_session.add_all(
        [
            Role(
                company_id=company.id,
                name="Administrator",
                is_system=True,
                system_key=(
                    SystemRoleKey.ADMINISTRATOR.value
                ),
            ),

            Role(
                company_id=company.id,
                name="Another Admin",
                is_system=True,
                system_key=(
                    SystemRoleKey.ADMINISTRATOR.value
                ),
            ),
        ]
    )

    with pytest.raises(
        IntegrityError
    ):
        await db_session.flush()


@pytest.mark.asyncio
async def test_different_companies_can_have_same_system_role_key(
    db_session: AsyncSession,
):
    company_a = await create_company(
        db_session,
        name="Company A",
    )

    company_b = await create_company(
        db_session,
        name="Company B",
    )

    role_a = Role(
        company_id=company_a.id,
        name="Administrator",
        is_system=True,
        system_key=(
            SystemRoleKey.ADMINISTRATOR.value
        ),
    )

    role_b = Role(
        company_id=company_b.id,
        name="Administrator",
        is_system=True,
        system_key=(
            SystemRoleKey.ADMINISTRATOR.value
        ),
    )

    db_session.add_all(
        [
            role_a,
            role_b,
        ]
    )

    await db_session.flush()

    assert role_a.id != role_b.id


@pytest.mark.asyncio
async def test_system_role_is_resolved_by_key_not_name(
    db_session: AsyncSession,
):
    company = await create_company(
        db_session,
        name="Main Company",
    )

    role = Role(
        company_id=company.id,
        name="Administrator",
        is_system=True,
        system_key=(
            SystemRoleKey.ADMINISTRATOR.value
        ),
    )

    db_session.add(
        role
    )

    await db_session.flush()

    original_id = role.id

    #
    # Display name изменился.
    #
    role.name = "Super Administrator"

    await db_session.flush()

    found = await get_system_role_by_key(
        db_session,
        company_id=company.id,
        system_key=(
            SystemRoleKey.ADMINISTRATOR.value
        ),
    )

    assert found is not None
    assert found.id == original_id

    assert (
        found.name
        == "Super Administrator"
    )