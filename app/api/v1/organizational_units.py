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

from schemas.organizational_units import (
    OrganizationalUnitCreate,
    OrganizationalUnitResponse,
    OrganizationalUnitUpdate,
)

from services.organizational_units import (
    CompanyNotFoundError,
    OrganizationalUnitHierarchyCycleError,
    OrganizationalUnitNotFoundError,
    ParentOrganizationalUnitNotFoundError,
    ParentOrganizationalUnitWrongCompanyError,
    create_new_organizational_unit,
    get_organizational_unit,
    list_organizational_units,
    update_organizational_unit,
)


router = APIRouter(
    prefix="/companies/{company_id}/units",
    tags=["Organizational Units"],
)


@router.get(
    "",
    response_model=list[
        OrganizationalUnitResponse
    ],
)
async def get_units_endpoint(
    company_id: int,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],

    _: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> list[OrganizationalUnitResponse]:
    try:
        return await list_organizational_units(
            session,
            company_id,
        )

    except CompanyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )


@router.get(
    "/{unit_id}",
    response_model=OrganizationalUnitResponse,
)
async def get_unit_endpoint(
    company_id: int,
    unit_id: int,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],

    _: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> OrganizationalUnitResponse:
    try:
        return await get_organizational_unit(
            session,
            company_id=company_id,
            unit_id=unit_id,
        )

    except OrganizationalUnitNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organizational unit not found",
        )


@router.post(
    "",
    response_model=OrganizationalUnitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_unit_endpoint(
    company_id: int,
    data: OrganizationalUnitCreate,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],

    _: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> OrganizationalUnitResponse:
    try:
        return await create_new_organizational_unit(
            session,
            company_id,
            data,
        )

    except CompanyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    except ParentOrganizationalUnitNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parent organizational unit not found",
        )

    except ParentOrganizationalUnitWrongCompanyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Parent organizational unit belongs "
                "to another company"
            ),
        )


@router.patch(
    "/{unit_id}",
    response_model=OrganizationalUnitResponse,
)
async def update_unit_endpoint(
    company_id: int,
    unit_id: int,
    data: OrganizationalUnitUpdate,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],

    _: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> OrganizationalUnitResponse:
    try:
        return await update_organizational_unit(
            session,
            company_id=company_id,
            unit_id=unit_id,
            data=data,
        )

    except OrganizationalUnitNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organizational unit not found",
        )

    except ParentOrganizationalUnitNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parent organizational unit not found",
        )

    except ParentOrganizationalUnitWrongCompanyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Parent organizational unit belongs "
                "to another company"
            ),
        )

    except OrganizationalUnitHierarchyCycleError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organizational unit hierarchy cycle detected",
        )