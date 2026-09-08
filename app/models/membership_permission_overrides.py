from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    UniqueConstraint,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from core.permissions.effects import (
    PermissionOverrideEffect,
)

from core.permissions.scopes import (
    PermissionScope,
)

from database.base import Base


class MembershipPermissionOverride(Base):
    __tablename__ = (
        "membership_permission_overrides"
    )

    __table_args__ = (
        UniqueConstraint(
            "company_membership_id",
            "permission_id",
            name=(
                "uq_membership_permission_overrides_"
                "membership_permission"
            ),
        ),

        CheckConstraint(
            (
                "(effect = 'allow' "
                "AND scope IS NOT NULL) "
                "OR "
                "(effect = 'deny' "
                "AND scope IS NULL)"
            ),
            name=(
                "ck_membership_permission_overrides_"
                "effect_scope"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    company_membership_id: Mapped[int] = (
        mapped_column(
            BigInteger,
            ForeignKey(
                "company_memberships.id",
                ondelete="CASCADE",
            ),
            nullable=False,
            index=True,
        )
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

    effect: Mapped[
        PermissionOverrideEffect
    ] = mapped_column(
        Enum(
            PermissionOverrideEffect,
            name="permission_override_effect",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=16,
            values_callable=lambda enum_cls: [
                item.value
                for item in enum_cls
            ],
        ),
        nullable=False,
    )

    scope: Mapped[
        PermissionScope | None
    ] = mapped_column(
        Enum(
            PermissionScope,
            name="permission_override_scope",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=32,
        ),
        nullable=True,
    )