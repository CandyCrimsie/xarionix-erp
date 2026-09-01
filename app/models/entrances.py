from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Entrance(Base):
    __tablename__ = "entrances"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    building_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("buildings.id"),
        nullable=False,
        index=True,
    )
    number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )