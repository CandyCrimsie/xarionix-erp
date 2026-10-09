from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class AddressTypeCategory(StrEnum):
    COUNTRY = "country"
    REGION = "region"
    LOCALITY = "locality"
    AREA = "area"
    THOROUGHFARE = "thoroughfare"


class AddressType(Base):
    __tablename__ = "address_types"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )
    category: Mapped[AddressTypeCategory] = mapped_column(
        Enum(
            AddressTypeCategory,
            name="address_type_category",
            values_callable=lambda enum: [
                item.value for item in enum
            ],
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    short_name: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default="100",
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
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
