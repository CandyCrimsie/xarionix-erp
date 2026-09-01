from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    address_object_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("address_objects.id"),
        nullable=False,
        index=True,
    )
    number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    corpus: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    structure: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )
    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )