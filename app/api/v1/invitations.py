from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
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
from dependencies.auth import (
    CurrentAuth,
    get_current_auth,
)
from dependencies.company import (
    CurrentCompanyContext,
    ensure_company_matches_context,
)
from dependencies.database import get_session
from models.company_invitations import (
    CompanyInvitation,
)
from repositories.company_invitations import (
    CompanyInvitationRecord,
)
from schemas.invitations import (
    CompanyInvitationCreate,
    CompanyInvitationCreatedResponse,
    CompanyInvitationResponse,
    InvitationListScope,
    InvitationAcceptNewUserRequest,
    InvitationAcceptanceResponse,
    InvitationPublicCompanyResponse,
    InvitationPublicResponse,
)
from services.invitations import (
    InvitationAcceptedError,
    InvitationExpiredError,
    InvitationInvalidExpirationError,
    InvitationNotFoundError,
    InvitationRevokedError,
    InvitationUserAlreadyExistsError,
    InvitationMembershipAlreadyExistsError,
    InvitationCompanyUnavailableError,
    accept_invitation_for_existing_user,
    accept_invitation_for_new_user,
    create_invitation,
    get_public_invitation,
    get_invitation_status,
    list_invitations,
    revoke_invitation,
)


router = APIRouter(
    tags=["Invitations"],
)


def _raise_acceptance_error(
    exc: Exception,
) -> None:
    if isinstance(exc, InvitationNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    if isinstance(exc, InvitationExpiredError):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Invitation has expired",
        )

    if isinstance(exc, InvitationRevokedError):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Invitation has been revoked",
        )

    if isinstance(exc, InvitationAcceptedError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invitation has already been accepted",
        )

    if isinstance(
        exc,
        InvitationUserAlreadyExistsError,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this username already exists",
        )

    if isinstance(
        exc,
        InvitationMembershipAlreadyExistsError,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "User is already a member of this company"
            ),
        )

    if isinstance(
        exc,
        InvitationCompanyUnavailableError,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company is inactive or unavailable",
        )

    raise exc


@router.get(
    "/invitations/{token}",
    response_model=InvitationPublicResponse,
)
async def get_public_invitation_endpoint(
    token: str,
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> InvitationPublicResponse:
    try:
        invitation, company = (
            await get_public_invitation(
                session,
                token=token,
            )
        )

    except InvitationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    return InvitationPublicResponse(
        company=InvitationPublicCompanyResponse(
            name=company.name,
            short_name=company.short_name,
        ),
        expires_at=invitation.expires_at,
        status=get_invitation_status(invitation),
    )


@router.post(
    "/invitations/{token}/accept",
    response_model=InvitationAcceptanceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def accept_invitation_new_user_endpoint(
    token: str,
    data: InvitationAcceptNewUserRequest,
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> InvitationAcceptanceResponse:
    try:
        user, company = (
            await accept_invitation_for_new_user(
                session,
                token=token,
                username=data.username,
                password=data.password,
            )
        )

    except (
        InvitationNotFoundError,
        InvitationExpiredError,
        InvitationRevokedError,
        InvitationAcceptedError,
        InvitationUserAlreadyExistsError,
        InvitationCompanyUnavailableError,
    ) as exc:
        _raise_acceptance_error(exc)

    return InvitationAcceptanceResponse(
        user=user,
        company_id=company.id,
    )


@router.post(
    "/invitations/{token}/accept-existing",
    response_model=InvitationAcceptanceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def accept_invitation_existing_user_endpoint(
    token: str,
    auth: Annotated[
        CurrentAuth,
        Depends(get_current_auth),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> InvitationAcceptanceResponse:
    try:
        company = (
            await accept_invitation_for_existing_user(
                session,
                token=token,
                user_id=auth.user.id,
            )
        )

    except (
        InvitationNotFoundError,
        InvitationExpiredError,
        InvitationRevokedError,
        InvitationAcceptedError,
        InvitationMembershipAlreadyExistsError,
        InvitationCompanyUnavailableError,
    ) as exc:
        _raise_acceptance_error(exc)

    return InvitationAcceptanceResponse(
        user=auth.user,
        company_id=company.id,
    )


def _invitation_response(
    invitation: CompanyInvitation,
    *,
    created_by_username: str,
) -> CompanyInvitationResponse:
    return CompanyInvitationResponse(
        id=invitation.id,
        company_id=invitation.company_id,
        token_prefix=(
            invitation.token_prefix
        ),
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        revoked_at=invitation.revoked_at,
        created_at=invitation.created_at,
        updated_at=invitation.updated_at,
        status=get_invitation_status(
            invitation
        ),
        created_by_username=(
            created_by_username
        ),
    )


def _record_response(
    record: CompanyInvitationRecord,
) -> CompanyInvitationResponse:
    return _invitation_response(
        record.invitation,
        created_by_username=(
            record.created_by_username
        ),
    )


@router.get(
    "/companies/{company_id}/invitations",
    response_model=(
        list[CompanyInvitationResponse]
    ),
)
async def list_company_invitations_endpoint(
    company_id: int,
    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.MEMBERS_MANAGE,
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
    scope: Annotated[
        InvitationListScope,
        Query(),
    ] = InvitationListScope.MINE,
) -> list[CompanyInvitationResponse]:
    ensure_company_matches_context(
        company_id=company_id,
        context=context,
    )

    records = await list_invitations(
        session,
        company_id=company_id,
        current_membership_id=(
            context.membership.id
        ),
        scope=scope,
    )

    return [
        _record_response(record)
        for record in records
    ]


@router.post(
    "/companies/{company_id}/invitations",
    response_model=(
        CompanyInvitationCreatedResponse
    ),
    status_code=status.HTTP_201_CREATED,
)
async def create_company_invitation_endpoint(
    company_id: int,
    data: CompanyInvitationCreate,
    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.MEMBERS_MANAGE,
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
) -> CompanyInvitationCreatedResponse:
    ensure_company_matches_context(
        company_id=company_id,
        context=context,
    )

    try:
        invitation, token = (
            await create_invitation(
                session,
                company_id=company_id,
                created_by_membership_id=(
                    context.membership.id
                ),
                expires_in_hours=(
                    data.expires_in_hours
                ),
            )
        )

    except InvitationInvalidExpirationError:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            detail=(
                "Invitation expiration is outside "
                "the allowed range"
            ),
        )

    response = _invitation_response(
        invitation,
        created_by_username=(
            context.user.username
        ),
    )

    return CompanyInvitationCreatedResponse(
        **response.model_dump(),
        token=token,
    )


@router.post(
    (
        "/companies/{company_id}"
        "/invitations/{invitation_id}"
        "/revoke"
    ),
    response_model=CompanyInvitationResponse,
)
async def revoke_company_invitation_endpoint(
    company_id: int,
    invitation_id: int,
    context: Annotated[
        CurrentCompanyContext,
        Depends(
            require_permission(
                PermissionCode.MEMBERS_MANAGE,
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
) -> CompanyInvitationResponse:
    ensure_company_matches_context(
        company_id=company_id,
        context=context,
    )

    try:
        record = await revoke_invitation(
            session,
            company_id=company_id,
            invitation_id=invitation_id,
        )

    except InvitationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    except InvitationAcceptedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Accepted invitation cannot "
                "be revoked"
            ),
        )

    except InvitationExpiredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Expired invitation cannot "
                "be revoked"
            ),
        )

    return _record_response(record)
