from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_user
from dependencies.database import get_session

from models.users import User

from schemas.unit_memberships import (
    UnitMembershipCreate,
    UnitMembershipResponse,
    UnitMembershipUpdate,
)

from services.unit_memberships import (
    CompanyMembershipNotFoundError,
    OrganizationalUnitNotFoundError,
    OrganizationalUnitWrongCompanyError,
    UnitMembershipAlreadyExistsError,
    UnitMembershipNotFoundError,
    add_membership_to_unit,
    get_membership_unit,
    list_membership_units,
    update_membership_unit,
)


router = APIRouter(
    prefix="/company-memberships/{company_membership_id}/units",
    tags=["Unit Memberships"],
)


@router.get(
    "",
    response_model=list[
        UnitMembershipResponse
    ],
)
async def get_membership_units_endpoint(
    company_membership_id: int,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],

    _: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> list[UnitMembershipResponse]:
    try:
        return await list_membership_units(
            session,
            company_membership_id,
        )

    except CompanyMembershipNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company membership not found",
        )


@router.post(
    "",
    response_model=UnitMembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_membership_unit_endpoint(
    company_membership_id: int,
    data: UnitMembershipCreate,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],

    _: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> UnitMembershipResponse:
    try:
        return await add_membership_to_unit(
            session,
            company_membership_id=company_membership_id,
            unit_id=data.unit_id,
            is_primary=data.is_primary,
        )

    except CompanyMembershipNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company membership not found",
        )

    except OrganizationalUnitNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organizational unit not found",
        )

    except OrganizationalUnitWrongCompanyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Organizational unit belongs "
                "to another company"
            ),
        )

    except UnitMembershipAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Membership is already assigned "
                "to this organizational unit"
            ),
        )


@router.get(
    "/{unit_membership_id}",
    response_model=UnitMembershipResponse,
)
async def get_membership_unit_endpoint(
    company_membership_id: int,
    unit_membership_id: int,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],

    _: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> UnitMembershipResponse:
    try:
        return await get_membership_unit(
            session,
            company_membership_id=company_membership_id,
            unit_membership_id=unit_membership_id,
        )

    except UnitMembershipNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unit membership not found",
        )


@router.patch(
    "/{unit_membership_id}",
    response_model=UnitMembershipResponse,
)
async def update_membership_unit_endpoint(
    company_membership_id: int,
    unit_membership_id: int,
    data: UnitMembershipUpdate,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],

    _: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> UnitMembershipResponse:
    try:
        return await update_membership_unit(
            session,
            company_membership_id=company_membership_id,
            unit_membership_id=unit_membership_id,
            is_primary=data.is_primary,
            is_active=data.is_active,
        )

    except UnitMembershipNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unit membership not found",
        )