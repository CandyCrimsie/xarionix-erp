import hashlib
import secrets

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from core.config import config
from core.security.password import hash_password
from models.company import Company
from models.company_invitations import (
    CompanyInvitation,
)
from models.users import User
from repositories.company_invitations import (
    CompanyInvitationRecord,
    create_company_invitation,
    get_company_invitation_by_id,
    get_company_invitation_by_token_hash,
    get_company_invitation_record,
    list_company_invitations,
)
from repositories.company_memberships import (
    create_company_membership,
    get_company_membership_by_user,
)
from repositories.company import get_company_by_id
from repositories.users import (
    create_user,
    get_user_by_username,
)
from schemas.invitations import (
    InvitationListScope,
    InvitationStatus,
)


class InvitationNotFoundError(Exception):
    pass


class InvitationInvalidExpirationError(
    Exception
):
    pass


class InvitationAcceptedError(Exception):
    pass


class InvitationExpiredError(Exception):
    pass


class InvitationRevokedError(Exception):
    pass


class InvitationUserAlreadyExistsError(Exception):
    pass


class InvitationMembershipAlreadyExistsError(
    Exception
):
    pass


class InvitationCompanyUnavailableError(
    Exception
):
    pass


def hash_invitation_token(
    token: str,
) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def get_invitation_status(
    invitation: CompanyInvitation,
    *,
    now: datetime | None = None,
) -> InvitationStatus:
    if invitation.revoked_at is not None:
        return InvitationStatus.REVOKED

    if invitation.accepted_at is not None:
        return InvitationStatus.ACCEPTED

    current_time = (
        now
        if now is not None
        else datetime.now(timezone.utc)
    )

    if invitation.expires_at <= current_time:
        return InvitationStatus.EXPIRED

    return InvitationStatus.PENDING


def _ensure_invitation_pending(
    invitation: CompanyInvitation,
) -> None:
    invitation_status = get_invitation_status(
        invitation
    )

    if invitation_status == InvitationStatus.REVOKED:
        raise InvitationRevokedError

    if invitation_status == InvitationStatus.ACCEPTED:
        raise InvitationAcceptedError

    if invitation_status == InvitationStatus.EXPIRED:
        raise InvitationExpiredError


async def get_public_invitation(
    session: AsyncSession,
    *,
    token: str,
) -> tuple[CompanyInvitation, Company]:
    invitation = (
        await get_company_invitation_by_token_hash(
            session,
            hash_invitation_token(token),
        )
    )

    if invitation is None:
        raise InvitationNotFoundError

    company = await get_company_by_id(
        session,
        invitation.company_id,
    )

    if company is None or not company.is_active:
        raise InvitationCompanyUnavailableError

    return invitation, company


async def _lock_pending_invitation(
    session: AsyncSession,
    *,
    token: str,
) -> tuple[CompanyInvitation, Company]:
    invitation = (
        await get_company_invitation_by_token_hash(
            session,
            hash_invitation_token(token),
            for_update=True,
        )
    )

    if invitation is None:
        raise InvitationNotFoundError

    _ensure_invitation_pending(invitation)

    company = await get_company_by_id(
        session,
        invitation.company_id,
    )

    if company is None or not company.is_active:
        raise InvitationCompanyUnavailableError

    return invitation, company


async def accept_invitation_for_new_user(
    session: AsyncSession,
    *,
    token: str,
    username: str,
    password: str,
) -> tuple[User, Company]:
    try:
        invitation, company = (
            await _lock_pending_invitation(
                session,
                token=token,
            )
        )

        existing_user = await get_user_by_username(
            session,
            username,
        )

        if existing_user is not None:
            raise InvitationUserAlreadyExistsError

        user = await create_user(
            session,
            username=username,
            password_hash=hash_password(password),
        )

        await create_company_membership(
            session,
            user_id=user.id,
            company_id=company.id,
        )

        invitation.accepted_at = (
            datetime.now(timezone.utc)
        )
        invitation.accepted_by_user_id = user.id

        await session.commit()
        await session.refresh(user)

        return user, company

    except IntegrityError as exc:
        await session.rollback()

        raise InvitationUserAlreadyExistsError from exc

    except Exception:
        if session.in_transaction():
            await session.rollback()

        raise


async def accept_invitation_for_existing_user(
    session: AsyncSession,
    *,
    token: str,
    user_id: int,
) -> Company:
    try:
        invitation, company = (
            await _lock_pending_invitation(
                session,
                token=token,
            )
        )

        existing_membership = (
            await get_company_membership_by_user(
                session,
                company_id=company.id,
                user_id=user_id,
            )
        )

        if existing_membership is not None:
            raise (
                InvitationMembershipAlreadyExistsError
            )

        await create_company_membership(
            session,
            user_id=user_id,
            company_id=company.id,
        )

        invitation.accepted_at = (
            datetime.now(timezone.utc)
        )
        invitation.accepted_by_user_id = user_id

        await session.commit()

        return company

    except IntegrityError as exc:
        await session.rollback()

        raise (
            InvitationMembershipAlreadyExistsError
        ) from exc

    except Exception:
        if session.in_transaction():
            await session.rollback()

        raise


async def create_invitation(
    session: AsyncSession,
    *,
    company_id: int,
    created_by_membership_id: int,
    expires_in_hours: int | None,
) -> tuple[
    CompanyInvitation,
    str,
]:
    lifetime_hours = (
        expires_in_hours
        if expires_in_hours is not None
        else config
            .INVITATION_DEFAULT_EXPIRE_HOURS
    )

    if (
        lifetime_hours < 1
        or lifetime_hours
        > config.INVITATION_MAX_EXPIRE_HOURS
    ):
        raise InvitationInvalidExpirationError

    token = secrets.token_urlsafe(
        config.INVITATION_TOKEN_BYTES
    )

    now = datetime.now(timezone.utc)

    invitation = (
        await create_company_invitation(
            session,
            company_id=company_id,
            created_by_membership_id=(
                created_by_membership_id
            ),
            token_hash=(
                hash_invitation_token(
                    token
                )
            ),
            token_prefix=token[:8],
            expires_at=(
                now
                + timedelta(
                    hours=lifetime_hours
                )
            ),
        )
    )

    await session.commit()
    await session.refresh(invitation)

    return invitation, token


async def list_invitations(
    session: AsyncSession,
    *,
    company_id: int,
    current_membership_id: int,
    scope: InvitationListScope,
) -> list[CompanyInvitationRecord]:
    created_by_membership_id = (
        current_membership_id
        if scope
        == InvitationListScope.MINE
        else None
    )

    return await list_company_invitations(
        session,
        company_id=company_id,
        created_by_membership_id=(
            created_by_membership_id
        ),
    )


async def revoke_invitation(
    session: AsyncSession,
    *,
    company_id: int,
    invitation_id: int,
) -> CompanyInvitationRecord:
    try:
        invitation = (
            await get_company_invitation_by_id(
                session,
                company_id=company_id,
                invitation_id=invitation_id,
                for_update=True,
            )
        )

        if invitation is None:
            raise InvitationNotFoundError

        invitation_status = (
            get_invitation_status(
                invitation
            )
        )

        if (
            invitation_status
            == InvitationStatus.ACCEPTED
        ):
            raise InvitationAcceptedError

        if (
            invitation_status
            == InvitationStatus.EXPIRED
        ):
            raise InvitationExpiredError

        if (
            invitation_status
            == InvitationStatus.PENDING
        ):
            invitation.revoked_at = (
                datetime.now(timezone.utc)
            )

            await session.commit()
            await session.refresh(invitation)
        else:
            # Повторный revoke идемпотентен.
            await session.rollback()

        record = (
            await get_company_invitation_record(
                session,
                company_id=company_id,
                invitation_id=invitation_id,
            )
        )

        if record is None:
            raise InvitationNotFoundError

        return record

    except Exception:
        if session.in_transaction():
            await session.rollback()

        raise
