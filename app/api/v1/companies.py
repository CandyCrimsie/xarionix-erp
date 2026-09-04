from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from models.users import User
from dependencies.database import get_session
from schemas.company import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
)
from dependencies.auth import get_current_user
from services.company import (
    CompanyNotFoundError,
    CompanyParentCycleError,
    ParentCompanyNotFoundError,
    create_new_company,
    get_company,
    list_companies,
    update_company,
)


router = APIRouter(
    prefix="/companies",
    tags=["Companies"],
)


@router.get(
    "",
    response_model=list[CompanyResponse],
)
async def get_companies_endpoint(
    session: AsyncSession = Depends(
        get_session,
    ),
    _: User = Depends(
        get_current_user,
    ),
) -> list[CompanyResponse]:
    return await list_companies(session)


@router.get(
    "/{company_id}",
    response_model=CompanyResponse,
)
async def get_company_endpoint(
    company_id: int,
    session: AsyncSession = Depends(
        get_session,
    ),
    _: User = Depends(
        get_current_user,
    ),
) -> CompanyResponse:
    try:
        return await get_company(
            session,
            company_id,
        )

    except CompanyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )


@router.post(
    "",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_company_endpoint(
    data: CompanyCreate,
    session: AsyncSession = Depends(
        get_session,
    ),
    _: User = Depends(
        get_current_user,
    ),
) -> CompanyResponse:
    try:
        return await create_new_company(
            session,
            data,
        )

    except ParentCompanyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parent company not found",
        )


@router.patch(
    "/{company_id}",
    response_model=CompanyResponse,
)
async def update_company_endpoint(
    company_id: int,
    data: CompanyUpdate,
    session: AsyncSession = Depends(
        get_session,
    ),
    _: User = Depends(
        get_current_user,
    ),
) -> CompanyResponse:
    try:
        return await update_company(
            session,
            company_id,
            data,
        )

    except CompanyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    except ParentCompanyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parent company not found",
        )

    except CompanyParentCycleError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company hierarchy cycle detected",
        )