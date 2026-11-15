import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.database import DbSession
from app.core.deps import CurrentUser, require_admin
from app.modules.identity import service
from app.modules.identity.schemas import GlobalRoleUpdate, Token, UserCreate, UserRead

router = APIRouter()


@router.post("/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED, tags=["auth"])
def register(data: UserCreate, db: DbSession):
    return service.register_user(db, data)


@router.post("/auth/login", response_model=Token, tags=["auth"])
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    # OAuth2 form field is called "username"; we use it for the email.
    return Token(access_token=service.authenticate(db, form.username, form.password))


@router.get("/users/me", response_model=UserRead, tags=["users"])
def read_me(user: CurrentUser):
    return user


@router.patch(
    "/users/{user_id}/role",
    response_model=UserRead,
    tags=["users"],
    dependencies=[Depends(require_admin)],
)
def update_global_role(user_id: uuid.UUID, body: GlobalRoleUpdate, db: DbSession, actor: CurrentUser):
    return service.set_global_role(db, actor, user_id, body.global_role)
