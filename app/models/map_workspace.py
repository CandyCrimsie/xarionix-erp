"""Company organisation, personal display settings and on-demand passports.

Typed foreign keys, never an unchecked (entity_type, entity_id) reference.
Only membership/passport metadata cascades; network/address rows never do.
"""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class MapLayer(Base):
    __tablename__ = "map_layers"
    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_map_layers_company_id"),
        ForeignKeyConstraint(["company_id", "parent_id"], ["map_layers.company_id", "map_layers.id"], ondelete="RESTRICT"),
        CheckConstraint("mode IN ('group','manual','dynamic')", name="ck_map_layers_mode"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_map_layers_self_parent"),
        CheckConstraint("version > 0 AND jsonb_typeof(rules)='object'", name="ck_map_layers_data"),
        Index("ix_map_layers_tree", "company_id", "parent_id", "sort_order", "id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


TARGET_CHECK = "((building_id IS NOT NULL)::int + (marker_id IS NOT NULL)::int + (connection_id IS NOT NULL)::int) = 1"


class MapLayerMember(Base):
    __tablename__ = "map_layer_members"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "layer_id"], ["map_layers.company_id", "map_layers.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "marker_id"], ["map_markers.company_id", "map_markers.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "connection_id"], ["map_connections.company_id", "map_connections.id"], ondelete="CASCADE"),
        CheckConstraint(TARGET_CHECK, name="ck_map_layer_members_target"),
        UniqueConstraint("layer_id", "building_id", name="uq_map_layer_building"),
        UniqueConstraint("layer_id", "marker_id", name="uq_map_layer_marker"),
        UniqueConstraint("layer_id", "connection_id", name="uq_map_layer_connection"),
        Index("ix_map_layer_members_building", "company_id", "building_id", "layer_id"),
        Index("ix_map_layer_members_marker", "company_id", "marker_id", "layer_id"),
        Index("ix_map_layer_members_connection", "company_id", "connection_id", "layer_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    layer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    building_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("buildings.id", ondelete="CASCADE"))
    marker_id: Mapped[int | None] = mapped_column(BigInteger)
    connection_id: Mapped[int | None] = mapped_column(BigInteger)


class MapPreference(Base):
    __tablename__ = "map_preferences"
    __table_args__ = (CheckConstraint("version > 0 AND jsonb_typeof(settings)='object'", name="ck_map_preferences_data"),)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MapPassport(Base):
    __tablename__ = "map_passports"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "marker_id"], ["map_markers.company_id", "map_markers.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "connection_id"], ["map_connections.company_id", "map_connections.id"], ondelete="CASCADE"),
        CheckConstraint(TARGET_CHECK, name="ck_map_passports_target"),
        CheckConstraint("version > 0 AND jsonb_typeof(data)='object'", name="ck_map_passports_data"),
        UniqueConstraint("company_id", "building_id", name="uq_map_passport_building"),
        UniqueConstraint("company_id", "marker_id", name="uq_map_passport_marker"),
        UniqueConstraint("company_id", "connection_id", name="uq_map_passport_connection"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    building_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("buildings.id", ondelete="CASCADE"))
    marker_id: Mapped[int | None] = mapped_column(BigInteger)
    connection_id: Mapped[int | None] = mapped_column(BigInteger)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
