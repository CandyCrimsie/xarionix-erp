from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.company_invitations import (
    CompanyInvitation,
)
from models.company_memberships import (
    CompanyMembership,
)
from models.users import User


@dataclass(
    slots=True,
    frozen=True,
)
class CompanyInvitationRecord:
    invitation: CompanyInvitation
    created_by_username: str


async def create_company_invitation(
    session: AsyncSession,
    *,
    company_id: int,
    created_by_membership_id: int,
    token_hash: str,
    token_prefix: str,
    expires_at: datetime,
) -> CompanyInvitation:
    invitation = CompanyInvitation(
        company_id=company_id,
        created_by_membership_id=(
            created_by_membership_id
        ),
        token_hash=token_hash,
        token_prefix=token_prefix,
        expires_at=expires_at,
    )

    session.add(invitation)

    await session.flush()

    return invitation


def _invitation_record_statement():
    return (
        select(
            CompanyInvitation,
            User.username,
        )
        .join(
            CompanyMembership,
            CompanyMembership.id
            == CompanyInvitation
                .created_by_membership_id,
        )
        .join(
            User,
            User.id
            == CompanyMembership.user_id,
        )
    )


async def list_company_invitations(
    session: AsyncSession,
    *,
    company_id: int,
    created_by_membership_id: int | None = None,
) -> list[CompanyInvitationRecord]:
    stmt = (
        _invitation_record_statement()
        .where(
            CompanyInvitation.company_id
            == company_id
        )
    )

    if created_by_membership_id is not None:
        stmt = stmt.where(
            CompanyInvitation
                .created_by_membership_id
            == created_by_membership_id
        )

    stmt = stmt.order_by(
        CompanyInvitation.created_at.desc(),
        CompanyInvitation.id.desc(),
    )

    result = await session.execute(stmt)

    return [
        CompanyInvitationRecord(
            invitation=invitation,
            created_by_username=username,
        )
        for invitation, username
        in result.all()
    ]


async def get_company_invitation_record(
    session: AsyncSession,
    *,
    company_id: int,
    invitation_id: int,
) -> CompanyInvitationRecord | None:
    stmt = (
        _invitation_record_statement()
        .where(
            CompanyInvitation.id
            == invitation_id,
            CompanyInvitation.company_id
            == company_id,
        )
    )

    result = await session.execute(stmt)

    row = result.one_or_none()

    if row is None:
        return None

    invitation, username = row

    return CompanyInvitationRecord(
        invitation=invitation,
        created_by_username=username,
    )


async def get_company_invitation_by_id(
    session: AsyncSession,
    *,
    company_id: int,
    invitation_id: int,
    for_update: bool = False,
) -> CompanyInvitation | None:
    stmt = select(
        CompanyInvitation
    ).where(
        CompanyInvitation.id
        == invitation_id,
        CompanyInvitation.company_id
        == company_id,
    )

    if for_update:
        stmt = stmt.with_for_update()

    result = await session.execute(stmt)

    return result.scalar_one_or_none()


async def get_company_invitation_by_token_hash(
    session: AsyncSession,
    token_hash: str,
    *,
    for_update: bool = False,
) -> CompanyInvitation | None:
    stmt = select(
        CompanyInvitation
    ).where(
        CompanyInvitation.token_hash
        == token_hash
    )

    if for_update:
        stmt = stmt.with_for_update()

    result = await session.execute(stmt)

    return result.scalar_one_or_none()
