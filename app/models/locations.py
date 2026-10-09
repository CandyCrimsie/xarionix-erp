from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Location(Base):
    __tablename__ = "locations"

    __table_args__ = (
        ForeignKeyConstraint(
            ["entrance_id", "building_id"],
            ["entrances.id", "entrances.building_id"],
            name="fk_locations_entrance_building",
            ondelete="RESTRICT",
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
    building_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "buildings.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    entrance_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    floor: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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
