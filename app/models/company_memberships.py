from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from database.base import Base


class CompanyMembership(Base):
    __tablename__ = "company_memberships"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "company_id",
            name="uq_company_memberships_user_company",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
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

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)

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
