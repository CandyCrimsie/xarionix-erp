import pytest

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.permissions.codes import (
    PERMISSION_DEFINITIONS,
)
from core.system_roles import (
    SYSTEM_ROLE_TEMPLATES,
)

from models.company import Company

from repositories.permissions import (
    get_permissions,
)
from repositories.roles import (
    get_system_role_by_key,
)

from services.authorization_bootstrap import (
    sync_authorization_baseline,
)


@pytest.mark.asyncio
async def test_authorization_bootstrap_syncs_permissions_before_system_roles(
    db_session: AsyncSession,
    clean_test_redis,
):
    company_a = Company(
        name="Company A",
    )

    company_b = Company(
        name="Company B",
    )

    db_session.add_all(
        [
            company_a,
            company_b,
        ]
    )

    await db_session.flush()

    company_a_id = company_a.id
    company_b_id = company_b.id

    await db_session.commit()

    result = (
        await sync_authorization_baseline(
            db_session
        )
    )

    assert set(result) == {
        company_a_id,
        company_b_id,
    }

    permissions = await get_permissions(
        db_session,
        active_only=True,
    )

    assert {
        permission.code
        for permission in permissions
    } == {
        definition.code.value
        for definition
        in PERMISSION_DEFINITIONS
    }

    for company_id in (
        company_a_id,
        company_b_id,
    ):
        for template in (
            SYSTEM_ROLE_TEMPLATES
        ):
            role = (
                await get_system_role_by_key(
                    db_session,
                    company_id=company_id,
                    system_key=(
                        template.key.value
                    ),
                )
            )

            assert role is not None


@pytest.mark.asyncio
async def test_authorization_bootstrap_is_idempotent(
    db_session: AsyncSession,
    clean_test_redis,
):
    company = Company(
        name="Main Company",
    )

    db_session.add(
        company
    )

    await db_session.flush()

    company_id = company.id

    await db_session.commit()

    await sync_authorization_baseline(
        db_session
    )

    first_ids = {}

    for template in (
        SYSTEM_ROLE_TEMPLATES
    ):
        role = (
            await get_system_role_by_key(
                db_session,
                company_id=company_id,
                system_key=(
                    template.key.value
                ),
            )
        )

        assert role is not None

        first_ids[
            template.key.value
        ] = role.id

    await sync_authorization_baseline(
        db_session
    )

    second_ids = {}

    for template in (
        SYSTEM_ROLE_TEMPLATES
    ):
        role = (
            await get_system_role_by_key(
                db_session,
                company_id=company_id,
                system_key=(
                    template.key.value
                ),
            )
        )

        assert role is not None

        second_ids[
            template.key.value
        ] = role.id

    assert second_ids == first_ids