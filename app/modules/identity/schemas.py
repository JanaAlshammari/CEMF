import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.common.enums import GlobalRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=150)
    student_id: str | None = Field(default=None, max_length=30)
    department: str | None = Field(default=None, max_length=120)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    student_id: str | None
    department: str | None
    global_role: GlobalRole
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class GlobalRoleUpdate(BaseModel):
    global_role: GlobalRole
