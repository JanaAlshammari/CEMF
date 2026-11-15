import uuid
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, DateTime, ForeignKey, Integer,
                        String, Text, literal_column, text)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.base import Base, TimestampMixin, UUIDPKMixin
from app.common.enums import BookingStatus, ResourceType
from app.common.types import enum_col


class Resource(UUIDPKMixin, TimestampMixin, Base):
    """Venues (exclusive) and equipment (pooled by quantity)."""
    __tablename__ = "resources"
    __table_args__ = (
        CheckConstraint("total_quantity >= 1", name="qty_positive"),
        CheckConstraint("capacity IS NULL OR capacity > 0", name="capacity_positive"),
    )

    name: Mapped[str] = mapped_column(String(150), unique=True)
    resource_type: Mapped[ResourceType] = mapped_column(enum_col(ResourceType), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200))
    capacity: Mapped[int | None] = mapped_column(Integer)          # seats, for venues
    total_quantity: Mapped[int] = mapped_column(Integer, default=1)  # units, for equipment
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    bookings: Mapped[list["ResourceBooking"]] = relationship(back_populates="resource")


class ResourceBooking(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "resource_bookings"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="valid_time_range"),
        CheckConstraint("quantity >= 1", name="qty_positive"),
        # DB-level double-booking guard for EXCLUSIVE resources (venues).
        # Requires:  CREATE EXTENSION IF NOT EXISTS btree_gist;  (put in first migration)
        ExcludeConstraint(
            ("resource_id", "="),
            (literal_column("tstzrange(start_time, end_time, '[)')"), "&&"),
            where=text("is_exclusive AND status IN ('pending', 'approved')"),
            using="gist",
            name="ex_booking_no_overlap",
        ),
    )

    resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), index=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    # Denormalised from Resource.resource_type so the exclusion constraint can use it.
    # Set in the service layer: is_exclusive = (resource.resource_type == VENUE).
    is_exclusive: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[BookingStatus] = mapped_column(
        enum_col(BookingStatus), default=BookingStatus.PENDING, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    resource: Mapped[Resource] = relationship(back_populates="bookings")
