import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Index, String, Text,
                        UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.base import Base, TimestampMixin, UUIDPKMixin
from app.common.enums import ApplicationStatus, ClubRole, ClubStatus
from app.common.types import enum_col

if TYPE_CHECKING:
    from app.modules.identity.models import User


class Club(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "clubs"

    name: Mapped[str] = mapped_column(String(150), unique=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(60))
    logo_url: Mapped[str | None] = mapped_column(String(500))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[ClubStatus] = mapped_column(
        enum_col(ClubStatus), default=ClubStatus.ACTIVE
    )

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="club", cascade="all, delete-orphan"
    )
    applications: Mapped[list["MembershipApplication"]] = relationship(
        back_populates="club", cascade="all, delete-orphan"
    )
    activities: Mapped[list["ClubActivity"]] = relationship(
        back_populates="club", cascade="all, delete-orphan"
    )


class ClubActivity(UUIDPKMixin, TimestampMixin, Base):
    """Showcase entries on a club profile (past projects, regular programmes)."""
    __tablename__ = "club_activities"

    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    activity_date: Mapped[date | None] = mapped_column(Date)

    club: Mapped[Club] = relationship(back_populates="activities")


class Membership(UUIDPKMixin, TimestampMixin, Base):
    """Club-scoped role lives here: a user can be PRESIDENT of one club and
    a plain MEMBER of another."""
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("club_id", "user_id", name="uq_membership_club_user"),)

    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[ClubRole] = mapped_column(enum_col(ClubRole), default=ClubRole.MEMBER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    club: Mapped[Club] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")


class MembershipApplication(UUIDPKMixin, TimestampMixin, Base):
    """apply -> review -> accept/reject. Accepting creates a Membership row."""
    __tablename__ = "membership_applications"
    __table_args__ = (
        # A user may have only ONE pending application per club.
        Index(
            "uq_one_pending_application",
            "club_id", "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    statement: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ApplicationStatus] = mapped_column(
        enum_col(ApplicationStatus), default=ApplicationStatus.PENDING, index=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)

    club: Mapped[Club] = relationship(back_populates="applications")
