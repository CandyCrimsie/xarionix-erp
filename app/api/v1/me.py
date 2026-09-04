from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_user
from dependencies.database import get_session

from models.users import User

from schemas.company import CompanyResponse

from services.company_memberships import (
    list_available_companies_for_user,
)

from core.permissions.codes import PermissionCode

from dependencies.company import CurrentCompany
from services.authorization import AuthorizationService

from schemas.authorization import (
    EffectivePermissionsResponse,
)


router = APIRouter(
    prefix="/me",
    tags=["Current User"],
)


@router.get(
    "/companies",
    response_model=list[CompanyResponse],
)
async def get_my_companies(
    user: Annotated[
        User,
        Depends(get_current_user),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> list[CompanyResponse]:
    return await list_available_companies_for_user(
        session,
        user.id,
    )


@router.get(
    "/permissions",
    response_model=EffectivePermissionsResponse,
)
async def get_my_permissions(
    context: CurrentCompany,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> EffectivePermissionsResponse:
    authorization = AuthorizationService(
        session,
    )

    permissions = (
        await authorization.get_effective_permissions(
            company_id=context.company.id,
            company_membership_id=context.membership.id,
        )
    )

    return EffectivePermissionsResponse(
        permissions=sorted(permissions),
    )