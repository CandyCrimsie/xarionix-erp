from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

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
        ForeignKey(
            "address_objects.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )
    type_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "address_types.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    normalized_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
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

    parent: Mapped["AddressObject | None"] = relationship(
        "AddressObject",
        remote_side="AddressObject.id",
        back_populates="children",
    )
    children: Mapped[list["AddressObject"]] = relationship(
        "AddressObject",
        back_populates="parent",
    )


Index(
    "uq_address_objects_parent_type_normalized_name",
    func.coalesce(AddressObject.parent_id, 0),
    AddressObject.type_id,
    AddressObject.normalized_name,
    unique=True,
)
