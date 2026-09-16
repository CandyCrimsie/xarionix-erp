from typing import (
    Annotated,
)

from fastapi import (
    Depends,
    HTTPException,
    status,
)

from dependencies.auth import (
    CurrentAuth,
    get_current_auth,
)


async def require_system_admin(
    auth: Annotated[
        CurrentAuth,
        Depends(get_current_auth),
    ],
) -> CurrentAuth:
    if not auth.user.is_system_admin:
        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail=(
                "System administrator access required"
            ),
        )

    return auth