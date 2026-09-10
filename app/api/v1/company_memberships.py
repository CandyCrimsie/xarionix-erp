from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.company_memberships import (
    CompanyMembershipCreate,
    CompanyMembershipResponse,
    CompanyMembershipUpdate,
    CompanyMemberSummaryResponse,
)

from services.company_memberships import (
    CompanyMembershipAlreadyExistsError,
    CompanyMembershipNotFoundError,
    CompanyMembershipPermissionDeniedError,
    CompanyMembershipPrimaryUnitRequiredError,
    CompanyMembershipUnitNotFoundError,
    CompanyNotFoundError,
    UserNotFoundError,
    add_scoped_user_to_company,
    get_scoped_company_membership,
    list_scoped_company_memberships,
    update_scoped_company_membership,
    list_scoped_company_member_summaries,
)

from core.permissions.codes import (
    PermissionCode,
)

from dependencies.database import get_session
from dependencies.authorization import (
    require_permission,
)
from dependencies.company import (
    CurrentCompanyContext,
    ensure_company_matches_context,
)


router = APIRouter(
    prefix="/companies/{company_id}/members",
    tags=["Company Members"],
)


@router.get(
    "",
    response_model=list[
        CompanyMemberSummaryResponse
    ],
)
async def get_company_members_endpoint(
    company_id: int,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.MEMBERS_READ,
            )
        ),
    ],
) -> list[CompanyMemberSummaryResponse]:
    ensure_company_matches_context(
        company_id=company_id,
        context=context,
    )

    try:
        return (
            await list_scoped_company_member_summaries(
                session,
                company_id=company_id,
                current_membership_id=(
                    context.membership.id
                ),
            )
        )

    except CompanyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    except CompanyMembershipPermissionDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )


@router.get(
    "/{membership_id}",
    response_model=CompanyMembershipResponse,
)
async def get_company_member_endpoint(
    company_id: int,
    membership_id: int,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.MEMBERS_READ,
            )
        ),
    ],
) -> CompanyMembershipResponse:
    ensure_company_matches_context(
        company_id=company_id,
        context=context,
    )

    try:
        return await get_scoped_company_membership(
            session,
            company_id=company_id,
            membership_id=membership_id,
            current_membership_id=(
                context.membership.id
            ),
        )

    except CompanyMembershipNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company membership not found",
        )

    except CompanyMembershipPermissionDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )


@router.post(
    "",
    response_model=CompanyMembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_company_member_endpoint(
    company_id: int,
    data: CompanyMembershipCreate,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.MEMBERS_MANAGE,
            )
        ),
    ],
) -> CompanyMembershipResponse:
    ensure_company_matches_context(
        company_id=company_id,
        context=context,
    )

    try:
        return await add_scoped_user_to_company(
            session,
            company_id=company_id,
            user_id=data.user_id,
            current_membership_id=(
                context.membership.id
            ),
            primary_unit_id=(
                data.primary_unit_id
            ),
        )

    except CompanyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    except CompanyMembershipAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "User is already a member "
                "of this company"
            ),
        )

    except CompanyMembershipPrimaryUnitRequiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Primary unit is required "
                "for this permission scope"
            ),
        )

    except CompanyMembershipUnitNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organizational unit not found",
        )

    except CompanyMembershipPermissionDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )


@router.patch(
    "/{membership_id}",
    response_model=CompanyMembershipResponse,
)
async def update_company_member_endpoint(
    company_id: int,
    membership_id: int,
    data: CompanyMembershipUpdate,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.MEMBERS_MANAGE,
            )
        ),
    ],
) -> CompanyMembershipResponse:
    ensure_company_matches_context(
        company_id=company_id,
        context=context,
    )

    try:
        return await update_scoped_company_membership(
            session,
            company_id=company_id,
            membership_id=membership_id,
            current_membership_id=(
                context.membership.id
            ),
            is_active=data.is_active,
        )

    except CompanyMembershipNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company membership not found",
        )

    except CompanyMembershipPermissionDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )