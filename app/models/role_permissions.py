from sqlalchemy import (
    BigInteger,
    Enum,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from core.permissions.scopes import PermissionScope
from database.base import Base


class RolePermission(Base):
    __tablename__ = "role_permissions"

    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "permission_id",
            name="uq_role_permissions_role_permission",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "roles.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    permission_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "permissions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    scope: Mapped[PermissionScope] = mapped_column(
        Enum(
            PermissionScope,
            name="permission_scope",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=32,
        ),
        nullable=False,
        default=PermissionScope.COMPANY,
        server_default=PermissionScope.COMPANY.value,
    )