from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class AddressObject(Base):
    __tablename__ = "address_objects"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("address_objects.id"),
        nullable=True,
        index=True,
    )
    type_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("address_types.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )