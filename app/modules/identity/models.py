import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.base import Base, TimestampMixin, UUIDPKMixin
from app.common.enums import GlobalRole
from app.common.types import enum_col

if TYPE_CHECKING:
    from app.modules.clubs.models import Membership


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    student_id: Mapped[str | None] = mapped_column(String(30), unique=True)
    department: Mapped[str | None] = mapped_column(String(120))
    global_role: Mapped[GlobalRole] = mapped_column(
        enum_col(GlobalRole), default=GlobalRole.STUDENT, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
