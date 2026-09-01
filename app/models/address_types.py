from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class AddressType(Base):
    __tablename__ = "address_types"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )
    short_name: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )
    sort_order: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )