from sqlalchemy import (
    BigInteger,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from database.base import Base


class MembershipRole(Base):
    __tablename__ = "membership_roles"

    __table_args__ = (
        UniqueConstraint(
            "company_membership_id",
            "role_id",
            name="uq_membership_roles_membership_role",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    company_membership_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "company_memberships.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "roles.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )