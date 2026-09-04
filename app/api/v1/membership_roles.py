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

from schemas.membership_roles import (
    MembershipRolesUpdate,
)

from schemas.roles import (
    RoleResponse,
)

from services.membership_roles import (
    CompanyMembershipInactiveError,
    CompanyMembershipNotFoundError,
    InvalidRolesError,
    list_membership_roles,
    replace_membership_roles,
)


router = APIRouter(
    prefix="/members/{company_membership_id}/roles",
    tags=["Membership Roles"],
)


@router.get(
    "",
    response_model=list[RoleResponse],
)
async def get_membership_roles_endpoint(
    company_membership_id: int,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.MEMBERS_READ,
            )
        ),
    ],

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> list[RoleResponse]:
    try:
        return await list_membership_roles(
            session,
            company_id=context.company.id,
            company_membership_id=company_membership_id,
        )

    except CompanyMembershipNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company membership not found",
        )


@router.put(
    "",
    response_model=list[RoleResponse],
)
async def update_membership_roles_endpoint(
    company_membership_id: int,
    data: MembershipRolesUpdate,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.ROLES_ASSIGN,
            )
        ),
    ],

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> list[RoleResponse]:
    try:
        return await replace_membership_roles(
            session,
            company_id=context.company.id,
            company_membership_id=company_membership_id,
            role_ids=data.role_ids,
        )

    except CompanyMembershipNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company membership not found",
        )

    except CompanyMembershipInactiveError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company membership is inactive",
        )

    except InvalidRolesError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Invalid roles",
                "role_ids": exc.role_ids,
            },
        )