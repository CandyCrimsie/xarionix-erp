from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base
from core.map_routes import INSTALLATION_CHECK


class MapConnection(Base):
    __tablename__ = "map_connections"
    __table_args__ = (
        CheckConstraint("(source_building_id IS NULL) <> (source_marker_id IS NULL)", name="ck_map_connections_source"),
        CheckConstraint("(target_building_id IS NULL) <> (target_marker_id IS NULL)", name="ck_map_connections_target"),
        CheckConstraint("NOT (source_building_id IS NOT NULL AND target_building_id IS NOT NULL AND source_building_id = target_building_id) AND NOT (source_marker_id IS NOT NULL AND target_marker_id IS NOT NULL AND source_marker_id = target_marker_id)", name="ck_map_connections_different_ends"),
        CheckConstraint("visibility IN ('company', 'private') AND ((visibility = 'company' AND owner_user_id IS NULL) OR (visibility = 'private' AND owner_user_id IS NOT NULL))", name="ck_map_connections_visibility"),
        CheckConstraint("medium IN ('fiber', 'utp') AND ((medium = 'fiber' AND category IS NULL AND (fiber_count IS NULL OR fiber_count > 0)) OR (medium = 'utp' AND fiber_count IS NULL AND (category IS NULL OR category IN ('Cat 5e', 'Cat 6', 'Cat 6A'))))", name="ck_map_connections_medium"),
        CheckConstraint("status IN ('planned', 'construction', 'active', 'inactive')", name="ck_map_connections_status"),
        ForeignKeyConstraint(["company_id", "source_marker_id"], ["map_markers.company_id", "map_markers.id"], ondelete="RESTRICT", name="fk_map_connections_source_marker"),
        ForeignKeyConstraint(["company_id", "target_marker_id"], ["map_markers.company_id", "map_markers.id"], ondelete="RESTRICT", name="fk_map_connections_target_marker"),
        Index("ix_map_connections_context", "company_id", "visibility", "owner_user_id", "id"),
        UniqueConstraint("company_id", "id", name="uq_map_connections_company_id"),
        CheckConstraint(INSTALLATION_CHECK, name="ck_map_connections_installation"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"))
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="company")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_building_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("buildings.id", ondelete="RESTRICT"), index=True)
    target_building_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("buildings.id", ondelete="RESTRICT"), index=True)
    source_marker_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    target_marker_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    medium: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")
    fiber_count: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str | None] = mapped_column(String(16))
    vertices: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    installation_methods: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
