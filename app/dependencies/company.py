from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import (
    Depends,
    Header,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import (
    CurrentAuth,
    get_current_auth,
)
from dependencies.database import get_session

from models.company import Company
from models.company_memberships import CompanyMembership
from models.users import User

from repositories.company import (
    get_company_by_id,
)

from repositories.company_memberships import (
    get_company_membership_by_user,
)


@dataclass(slots=True, frozen=True)
class CurrentCompanyContext:
    user: User
    session_id: UUID

    company: Company
    membership: CompanyMembership


async def get_current_company_context(
    auth: Annotated[
        CurrentAuth,
        Depends(get_current_auth),
    ],

    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],

    company_id: Annotated[
        int | None,
        Header(
            alias="X-Company-Id",
            gt=0,
        ),
    ] = None,
) -> CurrentCompanyContext:
    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Company-Id header is required",
        )

    membership = await get_company_membership_by_user(
        session,
        company_id=company_id,
        user_id=auth.user.id,
    )

    if (
        membership is None
        or not membership.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company access denied",
        )

    company = await get_company_by_id(
        session,
        company_id,
    )

    if (
        company is None
        or not company.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company access denied",
        )

    return CurrentCompanyContext(
        user=auth.user,
        session_id=auth.session_id,
        company=company,
        membership=membership,
    )


CurrentCompany = Annotated[
    CurrentCompanyContext,
    Depends(get_current_company_context),
]