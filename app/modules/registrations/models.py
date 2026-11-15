import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.base import Base, TimestampMixin, UUIDPKMixin
from app.common.enums import RegistrationStatus
from app.common.types import enum_col


class Registration(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "registrations"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_registration_event_user"),)

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[RegistrationStatus] = mapped_column(
        enum_col(RegistrationStatus), default=RegistrationStatus.CONFIRMED, index=True
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ticket: Mapped["Ticket | None"] = relationship(
        back_populates="registration", uselist=False, cascade="all, delete-orphan"
    )


class Ticket(UUIDPKMixin, TimestampMixin, Base):
    """One digital ticket per confirmed registration. The QR image encodes
    `ticket_code`; `signature` (HMAC) lets the scanner reject forged codes."""
    __tablename__ = "tickets"

    registration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE"), unique=True
    )
    ticket_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    signature: Mapped[str] = mapped_column(String(128))
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    registration: Mapped[Registration] = relationship(back_populates="ticket")
