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
    CompanyChildCreate,
    CompanyMoveRequest,
    CompanyResponse,
    CompanyTreeNodeResponse,
    CompanyUpdate,
)

from services.company import (
    CompanyAdministratorRoleUnavailableError,
    CompanyInactiveParentError,
    CompanyNotFoundError,
    CompanyParentCycleError,
    CompanyRootMoveForbiddenError,
    ParentCompanyNotFoundError,
    create_child_company_with_administrator,
    get_company,
    get_company_tree,
    move_company_within_tree,
    update_company,
)


router = APIRouter(
    prefix="/companies",
    tags=["Companies"],
)


@router.post(
    "/{company_id}/children",
    response_model=CompanyResponse,
    status_code=(
        status.HTTP_201_CREATED
    ),
)
async def create_child_company_endpoint(
    company_id: int,
    data: CompanyChildCreate,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.COMPANIES_MANAGE,
                minimum_scope=(
                    PermissionScope.COMPANY
                ),
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
        return (
            await create_child_company_with_administrator(
                session,
                parent_company_id=company_id,
                administrator_user_id=(
                    context.user.id
                ),
                data=data,
            )
        )

    except ParentCompanyNotFoundError:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail="Company not found",
        )

    except (
        CompanyAdministratorRoleUnavailableError
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Company bootstrap failed"
            ),
        )


@router.get(
    "/{company_id}/tree",
    response_model=(
        CompanyTreeNodeResponse
    ),
)
async def get_company_tree_endpoint(
    company_id: int,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.COMPANIES_READ,
                minimum_scope=(
                    PermissionScope.COMPANY
                ),
            )
        ),
    ],

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> CompanyTreeNodeResponse:
    ensure_company_matches_context(
        company_id=company_id,
        context=context,
    )


    try:
        return await get_company_tree(
            session,
            company_id,
        )

    except CompanyNotFoundError:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail="Company not found",
        )


@router.patch(
    (
        "/{company_id}"
        "/tree/{target_company_id}"
        "/parent"
    ),
    response_model=CompanyResponse,
)
async def move_company_endpoint(
    company_id: int,
    target_company_id: int,
    data: CompanyMoveRequest,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.COMPANIES_MANAGE,
                minimum_scope=(
                    PermissionScope.COMPANY
                ),
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
        return await move_company_within_tree(
            session,
            root_company_id=company_id,
            company_id=target_company_id,
            parent_id=data.parent_id,
        )

    except CompanyNotFoundError:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail="Company not found",
        )

    except CompanyRootMoveForbiddenError:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "Root company cannot be moved"
            ),
        )

    except CompanyParentCycleError:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail=(
                "Company hierarchy cycle detected"
            ),
        )

    except ParentCompanyNotFoundError:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail="Company not found",
        )

    except CompanyInactiveParentError:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail=(
                "Active company cannot be moved "
                "under inactive company"
            ),
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