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
from schemas.employee import MyProfileResponse, EMPLOYEE_DETAIL_FIELDS

from services.company_memberships import (
    list_available_companies_for_user,
)

from dependencies.company import CurrentCompany
from services.authorization import AuthorizationService

from schemas.authorization import (
    EffectivePermissionsResponse,
)


router = APIRouter(
    prefix="/me",
    tags=["Current User"],
)


@router.get("/profile", response_model=MyProfileResponse)
async def get_my_profile(context: CurrentCompany) -> MyProfileResponse:
    return MyProfileResponse(
        user_id=context.user.id,
        username=context.user.username,
        company_id=context.company.id,
        company_name=context.company.name,
        account_created_at=context.user.created_at,
        joined_at=context.membership.created_at,
        **{field: getattr(context.membership, field) for field in EMPLOYEE_DETAIL_FIELDS},
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

    effective = (
        await authorization.get_effective_permissions(
            company_id=context.company.id,
            company_membership_id=context.membership.id,
        )
    )

    return EffectivePermissionsResponse(
        permissions=sorted(
            effective.keys()
        ),
        scopes={
            code: effective[code]
            for code in sorted(effective)
        },
    )
