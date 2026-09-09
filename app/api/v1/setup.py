from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.installation import (
    InstallationState,
)

from dependencies.database import (
    get_session,
)

from schemas.installation import (
    InstallationInitializeRequest,
    InstallationInitializeResponse,
    InstallationStatusResponse,
)

from services.installation import (
    AdministratorSystemRoleUnavailableError,
    InstallationNotAllowedError,
    get_installation_status,
    initialize_installation,
)


router = APIRouter(
    prefix="/setup",
    tags=["Setup"],
)


@router.get(
    "/status",
    response_model=(
        InstallationStatusResponse
    ),
)
async def get_setup_status_endpoint(
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> InstallationStatusResponse:
    installation_status = (
        await get_installation_status(
            session
        )
    )

    return InstallationStatusResponse(
        state=installation_status.state,
        setup_allowed=(
            installation_status
            .setup_allowed
        ),
    )


@router.post(
    "/initialize",
    response_model=(
        InstallationInitializeResponse
    ),
    status_code=(
        status.HTTP_201_CREATED
    ),
)
async def initialize_setup_endpoint(
    data: InstallationInitializeRequest,

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> InstallationInitializeResponse:
    try:
        result = (
            await initialize_installation(
                session,
                company_name=(
                    data.company.name
                ),
                company_short_name=(
                    data.company.short_name
                ),
                username=(
                    data.administrator.username
                ),
                password=(
                    data.administrator.password
                ),
            )
        )

    except InstallationNotAllowedError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail={
                "message": (
                    "Installation is "
                    "not allowed"
                ),
                "state": exc.state.value,
            },
        )

    except (
        AdministratorSystemRoleUnavailableError
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Installation bootstrap failed"
            ),
        )

    return (
        InstallationInitializeResponse(
            state=(
                InstallationState.INSTALLED
            ),
            company_id=(
                result.company.id
            ),
            company_name=(
                result.company.name
            ),
            user_id=result.user.id,
            username=result.user.username,
            membership_id=(
                result.membership.id
            ),
            administrator_role_id=(
                result.administrator_role.id
            ),
        )
    )