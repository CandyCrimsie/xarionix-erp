import pytest

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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


async def create_membership_with_units(
    session: AsyncSession,
):
    user = User(
        username="test-user",
        password_hash="test",
    )

    company = Company(
        name="Test Company",
    )

    session.add_all(
        [
            user,
            company,
        ]
    )

    await session.flush()

    membership = CompanyMembership(
        user_id=user.id,
        company_id=company.id,
    )

    unit_a = OrganizationalUnit(
        company_id=company.id,
        name="Support",
        type=(
            OrganizationalUnitType.DEPARTMENT
        ),
    )

    unit_b = OrganizationalUnit(
        company_id=company.id,
        name="NOC",
        type=(
            OrganizationalUnitType.DEPARTMENT
        ),
    )

    session.add_all(
        [
            membership,
            unit_a,
            unit_b,
        ]
    )

    await session.flush()

    return (
        membership,
        unit_a,
        unit_b,
    )


@pytest.mark.asyncio
async def test_membership_cannot_have_two_primary_units(
    db_session: AsyncSession,
):
    membership, unit_a, unit_b = (
        await create_membership_with_units(
            db_session
        )
    )

    db_session.add_all(
        [
            UnitMembership(
                company_membership_id=(
                    membership.id
                ),
                unit_id=unit_a.id,
                is_primary=True,
                is_active=True,
            ),
            UnitMembership(
                company_membership_id=(
                    membership.id
                ),
                unit_id=unit_b.id,
                is_primary=True,
                is_active=True,
            ),
        ]
    )

    with pytest.raises(
        IntegrityError
    ):
        await db_session.flush()


@pytest.mark.asyncio
async def test_primary_unit_must_be_active(
    db_session: AsyncSession,
):
    membership, unit_a, _ = (
        await create_membership_with_units(
            db_session
        )
    )

    db_session.add(
        UnitMembership(
            company_membership_id=(
                membership.id
            ),
            unit_id=unit_a.id,
            is_primary=True,
            is_active=False,
        )
    )

    with pytest.raises(
        IntegrityError
    ):
        await db_session.flush()