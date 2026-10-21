from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class MapMarker(Base):
    """Company-owned map annotation with an independent fixed position.

    ``building_id`` is an optional informational link. Coordinates are always
    owned by the marker and never follow later building-coordinate changes.
    """

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
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
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
