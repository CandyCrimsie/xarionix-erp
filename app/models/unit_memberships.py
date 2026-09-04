from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from database.base import Base


class UnitMembership(Base):
    __tablename__ = "unit_memberships"

    __table_args__ = (
        UniqueConstraint(
            "company_membership_id",
            "unit_id",
            name="uq_unit_memberships_membership_unit",
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
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "organizational_units.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
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