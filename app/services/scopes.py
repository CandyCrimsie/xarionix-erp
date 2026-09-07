from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.permissions.scopes import (
    PermissionScope,
)

from repositories.organizational_units import (
    get_unit_tree_ids,
)

from repositories.unit_memberships import (
    get_primary_unit_id,
)


class ScopeService:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    async def get_unit_ids(
        self,
        *,
        scope: PermissionScope,
        company_id: int,
        company_membership_id: int,
    ) -> set[int]:
        if scope not in {
            PermissionScope.OWN_UNIT,
            PermissionScope.OWN_UNIT_TREE,
        }:
            raise ValueError(
                "Scope is not unit-based"
            )

        primary_unit_id = (
            await get_primary_unit_id(
                self.session,
                company_membership_id,
            )
        )

        if primary_unit_id is None:
            return set()

        if scope == PermissionScope.OWN_UNIT:
            return {
                primary_unit_id
            }

        return await get_unit_tree_ids(
            self.session,
            company_id=company_id,
            unit_id=primary_unit_id,
        )