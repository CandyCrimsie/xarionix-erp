from sqlalchemy import (
    BigInteger,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from database.base import Base


class RoleDelegation(Base):
    __tablename__ = "role_delegations"

    __table_args__ = (
        UniqueConstraint(
            "manager_role_id",
            "assignable_role_id",
            name=(
                "uq_role_delegations_"
                "manager_assignable"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    manager_role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "roles.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    assignable_role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "roles.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )