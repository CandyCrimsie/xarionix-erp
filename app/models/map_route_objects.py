from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class MapRouteObject(Base):
    """Fixed-position marker on a route, NOT an electrical/optical endpoint."""
    __tablename__ = "map_route_objects"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "marker_id"], ["map_markers.company_id", "map_markers.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "connection_id"], ["map_connections.company_id", "map_connections.id"], ondelete="RESTRICT"),
        CheckConstraint("segment_index >= 0 AND fraction >= 0 AND fraction <= 1", name="ck_map_route_objects_position"),
        Index("ix_map_route_objects_connection", "company_id", "connection_id"),
    )
    marker_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    connection_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    fraction: Mapped[Decimal] = mapped_column(Numeric(16, 14), nullable=False)
    geometry_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
