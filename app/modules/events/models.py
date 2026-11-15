import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, Integer, Numeric,
                        String, Text, Boolean)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.base import Base, TimestampMixin, UUIDPKMixin
from app.common.enums import EventCategory, EventStatus
from app.common.types import enum_col


class Event(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="valid_time_range"),
        CheckConstraint("capacity > 0", name="capacity_positive"),
        CheckConstraint(
            "certificate_min_attendance BETWEEN 0 AND 100", name="threshold_pct_range"
        ),
    )

    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    venue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resources.id", ondelete="SET NULL")
    )

    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[EventCategory] = mapped_column(
        enum_col(EventCategory), default=EventCategory.OTHER, index=True
    )
    banner_url: Mapped[str | None] = mapped_column(String(500))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registration_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    capacity: Mapped[int] = mapped_column(Integer)  # must be <= venue capacity (service check)
    status: Mapped[EventStatus] = mapped_column(
        enum_col(EventStatus), default=EventStatus.DRAFT, index=True
    )

    # Certification rules
    certificate_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    certificate_min_attendance: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("75.00")
    )  # % of sessions an attendee must be scanned into

    sessions: Mapped[list["EventSession"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="EventSession.start_time"
    )


class EventSession(UUIDPKMixin, TimestampMixin, Base):
    """Every event has >=1 session. Attendance is logged per session, which lets
    multi-day workshops use a threshold (e.g. attend 3 of 4 sessions)."""
    __tablename__ = "event_sessions"
    __table_args__ = (CheckConstraint("end_time > start_time", name="valid_time_range"),)

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="Main Session")
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    event: Mapped[Event] = relationship(back_populates="sessions")
