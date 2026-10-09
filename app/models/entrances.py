from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Entrance(Base):
    __tablename__ = "entrances"

    __table_args__ = (
        Index(
            "uq_entrances_building_number",
            "building_id",
            "normalized_number",
            unique=True,
        ),
        UniqueConstraint(
            "id",
            "building_id",
            name="uq_entrances_id_building_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
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
    number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    normalized_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
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
