from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

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
)
from dependencies.database import (
    get_session,
)

from schemas.membership_permission_overrides import (
    MembershipPermissionOverrideResponse,
    MembershipPermissionOverrideUpdate,
)

from services.membership_permission_overrides import (
    CompanyMembershipInactiveError,
    CompanyMembershipNotFoundError,
    InvalidPermissionOverrideError,
    InvalidPermissionScopeError,
    PermissionInactiveError,
    PermissionNotFoundError,
    PermissionOverrideNotFoundError,
    delete_membership_permission_override,
    list_membership_permission_overrides,
    set_membership_permission_override,
)


router = APIRouter(
    prefix=(
        "/members/{company_membership_id}"
        "/permission-overrides"
    ),
    tags=[
        "Membership Permission Overrides"
    ],
)


@router.get(
    "",
    response_model=list[
        MembershipPermissionOverrideResponse
    ],
)
async def get_membership_permission_overrides_endpoint(
    company_membership_id: int,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.ROLES_MANAGE,
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
) -> list[
    MembershipPermissionOverrideResponse
]:
    try:
        return (
            await list_membership_permission_overrides(
                session,
                company_id=context.company.id,
                company_membership_id=(
                    company_membership_id
                ),
            )
        )

    except CompanyMembershipNotFoundError:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "Company membership not found"
            ),
        )


@router.put(
    "/{permission_id}",
    response_model=(
        MembershipPermissionOverrideResponse
    ),
)
async def set_membership_permission_override_endpoint(
    company_membership_id: int,
    permission_id: int,
    data: MembershipPermissionOverrideUpdate,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.ROLES_MANAGE,
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
) -> MembershipPermissionOverrideResponse:
    try:
        return (
            await set_membership_permission_override(
                session,
                company_id=context.company.id,
                company_membership_id=(
                    company_membership_id
                ),
                permission_id=permission_id,
                effect=data.effect,
                scope=data.scope,
            )
        )

    except CompanyMembershipNotFoundError:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "Company membership not found"
            ),
        )

    except CompanyMembershipInactiveError:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail=(
                "Company membership is inactive"
            ),
        )

    except PermissionNotFoundError:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail="Permission not found",
        )

    except PermissionInactiveError:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail="Permission is inactive",
        )

    except InvalidPermissionOverrideError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        )

    except InvalidPermissionScopeError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail={
                "message": (
                    "Invalid permission scope"
                ),
                "permission_id": (
                    exc.permission_id
                ),
                "code": exc.code,
                "scope": exc.scope.value,
                "allowed_scopes": [
                    scope.value
                    for scope
                    in exc.allowed_scopes
                ],
            },
        )


@router.delete(
    "/{permission_id}",
    status_code=(
        status.HTTP_204_NO_CONTENT
    ),
)
async def delete_membership_permission_override_endpoint(
    company_membership_id: int,
    permission_id: int,

    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.ROLES_MANAGE,
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
) -> Response:
    try:
        await delete_membership_permission_override(
            session,
            company_id=context.company.id,
            company_membership_id=(
                company_membership_id
            ),
            permission_id=permission_id,
        )

    except CompanyMembershipNotFoundError:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "Company membership not found"
            ),
        )

    except CompanyMembershipInactiveError:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail=(
                "Company membership is inactive"
            ),
        )

    except PermissionOverrideNotFoundError:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "Permission override not found"
            ),
        )

    return Response(
        status_code=(
            status.HTTP_204_NO_CONTENT
        )
    )