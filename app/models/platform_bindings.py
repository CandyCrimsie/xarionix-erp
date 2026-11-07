"""Additive, explicit identity bindings. No JIT users, email/name matching or ID casts."""

from datetime import datetime
from uuid import UUID

from database.base import Base
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column


class PlatformUserBinding(Base):
    __tablename__ = "platform_user_bindings"
    __table_args__ = (
        UniqueConstraint("core_api", "issuer", "subject"),
        UniqueConstraint("core_api", "user_id"),
    )
    core_api: Mapped[str] = mapped_column(String(512), primary_key=True)
    core_user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    issuer: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )


class PlatformCompanyBinding(Base):
    __tablename__ = "platform_company_bindings"
    __table_args__ = (UniqueConstraint("core_api", "company_id"),)
    core_api: Mapped[str] = mapped_column(String(512), primary_key=True)
    core_company_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )


class PlatformBindingAudit(Base):
    __tablename__ = "platform_binding_audit"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    operator: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    core_api: Mapped[str] = mapped_column(String(512))
    core_id: Mapped[UUID] = mapped_column(Uuid)
    erp_id: Mapped[int] = mapped_column(BigInteger)
