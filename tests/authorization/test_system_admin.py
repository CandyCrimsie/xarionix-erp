from uuid import uuid4

import pytest

from fastapi import (
    HTTPException,
)

from dependencies.auth import (
    CurrentAuth,
)

from dependencies.system_admin import (
    require_system_admin,
)

from models.users import User


@pytest.mark.asyncio
async def test_system_admin_is_allowed():
    user = User(
        id=1,
        username="admin",
        password_hash="hash",
        is_active=True,
        is_system_admin=True,
    )

    auth = CurrentAuth(
        user=user,
        session_id=uuid4(),
    )


    result = await require_system_admin(
        auth
    )


    assert result is auth


@pytest.mark.asyncio
async def test_regular_user_is_denied_system_admin_access():
    user = User(
        id=1,
        username="user",
        password_hash="hash",
        is_active=True,
        is_system_admin=False,
    )

    auth = CurrentAuth(
        user=user,
        session_id=uuid4(),
    )


    with pytest.raises(
        HTTPException
    ) as exc_info:
        await require_system_admin(
            auth
        )


    assert (
        exc_info.value.status_code
        == 403
    )

    assert (
        exc_info.value.detail
        == (
            "System administrator "
            "access required"
        )
    )