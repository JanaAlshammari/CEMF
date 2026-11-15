import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import ClubRole, ClubStatus


class ClubCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None
    category: str | None = Field(default=None, max_length=60)
    president_id: uuid.UUID  # the user who becomes the club's first president


class ClubRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    category: str | None
    status: ClubStatus


class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    club_id: uuid.UUID
    role: ClubRole
    is_active: bool


class MemberRoleUpdate(BaseModel):
    role: ClubRole


class MyClubRead(BaseModel):
    club_id: uuid.UUID
    club_name: str
    club_slug: str
    role: ClubRole
