from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    building_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("buildings.id"),
        nullable=True,
        index=True,
    )
    entrance_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("entrances.id"),
        nullable=True,
        index=True,
    )
    floor: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )