import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (DateTime, ForeignKey, Numeric, String, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin, UUIDPKMixin
from app.common.enums import AttendanceMethod
from app.common.types import enum_col


class AttendanceRecord(UUIDPKMixin, Base):
    __tablename__ = "attendance_records"
    # Scanning the same ticket twice for the same session is idempotent.
    __table_args__ = (UniqueConstraint("session_id", "ticket_id", name="uq_attendance_session_ticket"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("event_sessions.id", ondelete="CASCADE"), index=True
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)  # denormalised for fast reports
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    scanned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    method: Mapped[AttendanceMethod] = mapped_column(
        enum_col(AttendanceMethod), default=AttendanceMethod.QR_SCAN
    )
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Certificate(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "certificates"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_certificate_event_user"),)

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Public code printed on the certificate / used by a /verify/{code} endpoint.
    verification_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    attendance_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    file_path: Mapped[str | None] = mapped_column(String(500))  # generated PDF, if cached
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
