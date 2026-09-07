from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions.codes import (
    PermissionCode,
)
from core.permissions.scopes import (
    PermissionScope,
)

from dependencies.authorization import (
    require_permission,
)
from dependencies.company import (
    CurrentCompanyContext,
    ensure_company_matches_context,
)
from dependencies.database import get_session

from schemas.company import (
    CompanyResponse,
    CompanyUpdate,
)

from services.company import (
    CompanyNotFoundError,
    get_company,
    update_company,
)


router = APIRouter(
    prefix="/companies",
    tags=["Companies"],
)


@router.get(
    "/{company_id}",
    response_model=CompanyResponse,
)
async def get_company_endpoint(
    company_id: int,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.COMPANIES_READ,
                minimum_scope=PermissionScope.COMPANY,
            )
        ),
    ],

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> CompanyResponse:
    ensure_company_matches_context(
        company_id=company_id,
        context=context,
    )

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


@router.patch(
    "/{company_id}",
    response_model=CompanyResponse,
)
async def update_company_endpoint(
    company_id: int,
    data: CompanyUpdate,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.COMPANIES_MANAGE,
                minimum_scope=PermissionScope.COMPANY,
            )
        ),
    ],

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> CompanyResponse:
    ensure_company_matches_context(
        company_id=company_id,
        context=context,
    )

    restricted_fields = {
        "parent_id",
        "is_active",
    }

    if (
        restricted_fields
        & data.model_fields_set
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "parent_id and is_active cannot "
                "be changed through this endpoint"
            ),
        )

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