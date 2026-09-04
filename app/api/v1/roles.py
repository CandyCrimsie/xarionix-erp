from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions.codes import PermissionCode

from dependencies.authorization import require_permission
from dependencies.company import CurrentCompanyContext
from dependencies.database import get_session

from schemas.roles import (
    RoleCreate,
    RoleResponse,
    RoleUpdate,
)

from services.roles import (
    RoleAlreadyExistsError,
    RoleNotFoundError,
    create_new_role,
    get_role,
    list_roles,
    update_role,
)


router = APIRouter(
    prefix="/roles",
    tags=["Roles"],
)


@router.get(
    "",
    response_model=list[RoleResponse],
)
async def get_roles_endpoint(
    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.ROLES_READ,
            )
        ),
    ],

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> list[RoleResponse]:
    return await list_roles(
        session,
        context.company.id,
    )


@router.post(
    "",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_role_endpoint(
    data: RoleCreate,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.ROLES_MANAGE,
            )
        ),
    ],

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> RoleResponse:
    try:
        return await create_new_role(
            session,
            company_id=context.company.id,
            data=data,
        )

    except RoleAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role with this name already exists",
        )


@router.get(
    "/{role_id}",
    response_model=RoleResponse,
)
async def get_role_endpoint(
    role_id: int,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.ROLES_READ,
            )
        ),
    ],

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> RoleResponse:
    try:
        return await get_role(
            session,
            company_id=context.company.id,
            role_id=role_id,
        )

    except RoleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )


@router.patch(
    "/{role_id}",
    response_model=RoleResponse,
)
async def update_role_endpoint(
    role_id: int,
    data: RoleUpdate,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.ROLES_MANAGE,
            )
        ),
    ],

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> RoleResponse:
    try:
        return await update_role(
            session,
            company_id=context.company.id,
            role_id=role_id,
            data=data,
        )

    except RoleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    except RoleAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role with this name already exists",
        )