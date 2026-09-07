from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions.codes import PermissionCode
from core.permissions.scopes import PermissionScope

from dependencies.authorization import (
    require_permission,
)
from dependencies.company import (
    CurrentCompanyContext,
)
from dependencies.database import get_session

from schemas.role_permissions import (
    RolePermissionResponse,
    RolePermissionsUpdate,
)

from services.role_permissions import (
    InvalidPermissionsError,
    RoleNotFoundError,
    list_role_permissions,
    replace_role_permissions,
)


router = APIRouter(
    prefix="/roles/{role_id}/permissions",
    tags=["Role Permissions"],
)


@router.get(
    "",
    response_model=list[RolePermissionResponse],
)
async def get_role_permissions_endpoint(
    role_id: int,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.ROLES_READ,
                minimum_scope=PermissionScope.COMPANY,
            )
        ),
    ],

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> list[RolePermissionResponse]:
    try:
        return await list_role_permissions(
            session,
            company_id=context.company.id,
            role_id=role_id,
        )

    except RoleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )


@router.put(
    "",
    response_model=list[RolePermissionResponse],
)
async def update_role_permissions_endpoint(
    role_id: int,
    data: RolePermissionsUpdate,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.ROLES_MANAGE,
                minimum_scope=PermissionScope.COMPANY,
            )
        ),
    ],

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> list[RolePermissionResponse]:
    try:
        return await replace_role_permissions(
            session,
            company_id=context.company.id,
            role_id=role_id,
            permissions=data.permissions,
        )

    except RoleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    except InvalidPermissionsError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Invalid permissions",
                "permission_ids": exc.permission_ids,
            },
        )