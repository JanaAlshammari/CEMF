import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin, UUIDPKMixin


class Feedback(UUIDPKMixin, TimestampMixin, Base):
    """One evaluation per attendee per event (eligibility = has attendance record,
    enforced in the service layer)."""
    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uq_feedback_event_user"),
        CheckConstraint("overall_rating BETWEEN 1 AND 5", name="overall_range"),
        CheckConstraint("content_rating IS NULL OR content_rating BETWEEN 1 AND 5", name="content_range"),
        CheckConstraint("organization_rating IS NULL OR organization_rating BETWEEN 1 AND 5", name="org_range"),
        CheckConstraint("venue_rating IS NULL OR venue_rating BETWEEN 1 AND 5", name="venue_range"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    overall_rating: Mapped[int] = mapped_column(SmallInteger)
    content_rating: Mapped[int | None] = mapped_column(SmallInteger)
    organization_rating: Mapped[int | None] = mapped_column(SmallInteger)
    venue_rating: Mapped[int | None] = mapped_column(SmallInteger)
    comments: Mapped[str | None] = mapped_column(Text)
    suggestions: Mapped[str | None] = mapped_column(Text)
    custom_answers: Mapped[dict | None] = mapped_column(JSONB)  # per-event extra survey questions
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
