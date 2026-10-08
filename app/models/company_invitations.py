from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from database.base import Base


class CompanyInvitation(Base):
    __tablename__ = "company_invitations"

    __table_args__ = (
        CheckConstraint(
            (
                "(accepted_at IS NULL "
                "AND accepted_by_user_id IS NULL) "
                "OR "
                "(accepted_at IS NOT NULL "
                "AND accepted_by_user_id IS NOT NULL)"
            ),
            name=(
                "ck_company_invitations_"
                "acceptance_consistency"
            ),
        ),
        CheckConstraint(
            "NOT (accepted_at IS NOT NULL "
            "AND revoked_at IS NOT NULL)",
            name=(
                "ck_company_invitations_"
                "accepted_or_revoked"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    company_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "companies.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    created_by_membership_id: Mapped[int] = (
        mapped_column(
            BigInteger,
            ForeignKey(
                "company_memberships.id",
                ondelete="RESTRICT",
            ),
            nullable=False,
            index=True,
        )
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    token_prefix: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    accepted_at: Mapped[datetime | None] = (
        mapped_column(
            DateTime(timezone=True),
            nullable=True,
        )
    )

    revoked_at: Mapped[datetime | None] = (
        mapped_column(
            DateTime(timezone=True),
            nullable=True,
        )
    )

    accepted_by_user_id: Mapped[int | None] = (
        mapped_column(
            BigInteger,
            ForeignKey(
                "users.id",
                ondelete="RESTRICT",
            ),
            nullable=True,
            index=True,
        )
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
