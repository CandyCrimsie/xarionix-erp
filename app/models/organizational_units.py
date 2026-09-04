from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from database.base import Base


class OrganizationalUnitType(StrEnum):
    DIVISION = "division"
    DEPARTMENT = "department"
    TEAM = "team"
    GROUP = "group"
    BRANCH = "branch"


class OrganizationalUnit(Base):
    __tablename__ = "organizational_units"

    __table_args__ = (
        CheckConstraint(
            "id <> parent_id",
            name="ck_organizational_units_not_self_parent",
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

    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "organizational_units.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    type: Mapped[OrganizationalUnitType] = mapped_column(
        Enum(
            OrganizationalUnitType,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=32,
        ),
        nullable=False,
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

    parent: Mapped[OrganizationalUnit | None] = relationship(
        "OrganizationalUnit",
        remote_side="OrganizationalUnit.id",
        back_populates="children",
    )

    children: Mapped[list[OrganizationalUnit]] = relationship(
        "OrganizationalUnit",
        back_populates="parent",
    )