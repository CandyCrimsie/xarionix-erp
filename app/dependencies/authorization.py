from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions.codes import (
    PermissionScope,
    PermissionCode
)

from dependencies.company import (
    CurrentCompany,
    CurrentCompanyContext,
)
from dependencies.database import get_session

from services.authorization import (
    AuthorizationService,
)


def require_permission(
    permission: PermissionCode | str,
    *,
    minimum_scope: PermissionScope | None = None,
):
    async def dependency(
        context: CurrentCompany,

        session: Annotated[
            AsyncSession,
            Depends(get_session),
        ],
    ) -> CurrentCompanyContext:
        authorization = AuthorizationService(
            session
        )

        allowed = await authorization.has_permission(
            company_id=context.company.id,
            company_membership_id=(
                context.membership.id
            ),
            permission=permission,
            minimum_scope=minimum_scope,
        )

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied",
            )

        return context

    return dependency