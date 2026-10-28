from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    text,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base
from core.map_markers import POINT_TYPE_CHECK


class MapMarker(Base):
    """Company/private point. Primary house styles use Building's canonical position."""

    __tablename__ = "map_markers"
    __table_args__ = (
        CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="ck_map_markers_latitude_range",
        ),
        CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="ck_map_markers_longitude_range",
        ),
        CheckConstraint(
            "icon_opacity >= 0 AND icon_opacity <= 1 "
            "AND text_opacity >= 0 AND text_opacity <= 1 "
            "AND background_opacity >= 0 AND background_opacity <= 1 "
            "AND border_opacity >= 0 AND border_opacity <= 1 "
            "AND marker_opacity >= 0 AND marker_opacity <= 1",
            name="ck_map_markers_opacity_range",
        ),
        CheckConstraint(
            "border_width >= 0 AND border_width <= 8",
            name="ck_map_markers_border_width_range",
        ),
        Index("ix_map_markers_company_coordinates", "company_id", "longitude", "latitude"),
        UniqueConstraint("company_id", "id", name="uq_map_markers_company_id"),
        CheckConstraint("visibility IN ('company', 'private') AND ((visibility = 'company' AND owner_user_id IS NULL) OR (visibility = 'private' AND owner_user_id IS NOT NULL))", name="ck_map_markers_visibility"),
        CheckConstraint("building_link_role IN ('none', 'reference', 'located_at', 'represents') AND ((building_link_role = 'none' AND building_id IS NULL) OR (building_link_role <> 'none' AND building_id IS NOT NULL))", name="ck_map_markers_building_link"),
        CheckConstraint("building_link_role <> 'represents' OR (visibility = 'company' AND point_type = 'building' AND latitude IS NULL AND longitude IS NULL)", name="ck_map_markers_represents"),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="ck_map_markers_coordinate_pair"),
        CheckConstraint(POINT_TYPE_CHECK, name="ck_map_markers_point_type"),
        Index("uq_map_markers_represents", "company_id", "building_id", unique=True, postgresql_where=text("building_link_role = 'represents'")),
        Index("ix_map_markers_visibility_owner", "company_id", "visibility", "owner_user_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    building_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("buildings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sync_building_coordinates: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="company", server_default="company")
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    point_type: Mapped[str] = mapped_column(String(24), nullable=False, default="note", server_default="note")
    building_link_role: Mapped[str] = mapped_column(String(16), nullable=False, default="none", server_default="none")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    icon_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    label_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    icon_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#FFFFFF")
    icon_opacity: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=1)
    text_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#FFFFFF")
    text_opacity: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=1)
    background_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    background_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#2563EB")
    background_opacity: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=0.9)
    border_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    border_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#FFFFFF")
    border_width: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False, default=2)
    border_opacity: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=1)
    marker_opacity: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=1)
    marker_size: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    marker_shape: Mapped[str] = mapped_column(String(24), nullable=False, default="rounded")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
