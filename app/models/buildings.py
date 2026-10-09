from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Building(Base):
    __tablename__ = "buildings"

    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR "
            "(latitude >= -90 AND latitude <= 90)",
            name="ck_buildings_latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR "
            "(longitude >= -180 AND longitude <= 180)",
            name="ck_buildings_longitude_range",
        ),
        Index(
            "uq_buildings_address_number_parts",
            "address_object_id",
            "normalized_number",
            "normalized_corpus",
            "normalized_structure",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    address_object_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "address_objects.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    normalized_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    corpus: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    normalized_corpus: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="",
        server_default="",
    )
    structure: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    normalized_structure: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="",
        server_default="",
    )
    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )
    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
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
