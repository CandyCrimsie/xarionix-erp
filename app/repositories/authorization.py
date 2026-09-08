from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.company_memberships import CompanyMembership
from models.membership_roles import MembershipRole
from models.permissions import Permission
from models.role_permissions import RolePermission
from models.roles import Role
from models.membership_permission_overrides import (
    MembershipPermissionOverride,
)

from core.permissions.scopes import (
    PermissionScope,
    get_broader_scope,
)

from core.permissions.effects import (
    PermissionOverrideEffect,
)


async def get_effective_permission_codes(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
) -> dict[str, PermissionScope]:
    #
    # 1. Собираем permissions из ролей.
    #
    role_stmt = (
        select(
            Permission.code,
            RolePermission.scope,
        )
        .join(
            RolePermission,
            RolePermission.permission_id
            == Permission.id,
        )
        .join(
            Role,
            Role.id
            == RolePermission.role_id,
        )
        .join(
            MembershipRole,
            MembershipRole.role_id
            == Role.id,
        )
        .join(
            CompanyMembership,
            CompanyMembership.id
            == MembershipRole.company_membership_id,
        )
        .where(
            CompanyMembership.id
            == company_membership_id,

            CompanyMembership.company_id
            == company_id,

            CompanyMembership.is_active.is_(
                True
            ),

            Role.company_id
            == company_id,

            Role.is_active.is_(
                True
            ),

            Permission.is_active.is_(
                True
            ),
        )
    )

    role_result = await session.execute(
        role_stmt
    )

    effective: dict[
        str,
        PermissionScope,
    ] = {}

    for code, scope in role_result.all():
        scope = PermissionScope(
            scope
        )

        current_scope = effective.get(
            code
        )

        if current_scope is None:
            effective[code] = scope
            continue

        effective[code] = get_broader_scope(
            current_scope,
            scope,
        )

    #
    # 2. Получаем индивидуальные overrides.
    #
    override_stmt = (
        select(
            Permission.code,
            MembershipPermissionOverride.effect,
            MembershipPermissionOverride.scope,
        )
        .join(
            MembershipPermissionOverride,
            MembershipPermissionOverride.permission_id
            == Permission.id,
        )
        .join(
            CompanyMembership,
            CompanyMembership.id
            == (
                MembershipPermissionOverride
                .company_membership_id
            ),
        )
        .where(
            CompanyMembership.id
            == company_membership_id,

            CompanyMembership.company_id
            == company_id,

            CompanyMembership.is_active.is_(
                True
            ),

            Permission.is_active.is_(
                True
            ),
        )
    )

    override_result = await session.execute(
        override_stmt
    )

    #
    # 3. Применяем overrides поверх ролей.
    #
    for (
        code,
        effect,
        scope,
    ) in override_result.all():
        effect = PermissionOverrideEffect(
            effect
        )

        #
        # DENY всегда финальный:
        # permission исчезает полностью.
        #
        if (
            effect
            == PermissionOverrideEffect.DENY
        ):
            effective.pop(
                code,
                None,
            )
            continue

        #
        # ALLOW по DB invariant всегда
        # обязан иметь scope.
        #
        if scope is None:
            continue

        override_scope = PermissionScope(
            scope
        )

        current_scope = effective.get(
            code
        )

        #
        # Право отсутствовало в ролях —
        # индивидуальный ALLOW его добавляет.
        #
        if current_scope is None:
            effective[code] = (
                override_scope
            )
            continue

        #
        # ALLOW может расширить permission,
        # но не сужает уже существующий scope.
        #
        effective[code] = (
            get_broader_scope(
                current_scope,
                override_scope,
            )
        )

    return effective


async def get_membership_ids_by_role(
    session: AsyncSession,
    role_id: int,
) -> list[int]:
    stmt = (
        select(
            MembershipRole.company_membership_id
        )
        .where(
            MembershipRole.role_id
            == role_id
        )
        .distinct()
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )