import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import GlobalRole
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.identity.models import User
from app.modules.identity.schemas import UserCreate

# Verified against when the email is unknown, so login time doesn't reveal which emails exist.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def register_user(db: Session, data: UserCreate) -> User:
    email = data.email.lower()
    clash = db.scalar(
        select(User).where(
            (User.email == email)
            | ((User.student_id == data.student_id) if data.student_id else False)
        )
    )
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or student ID already registered")

    user = User(
        email=email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        student_id=data.student_id,
        department=data.department,
        global_role=GlobalRole.STUDENT,  # self-registration is never privileged
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> str:
    user = db.scalar(select(User).where(User.email == email.lower()))
    ok = verify_password(password, user.hashed_password if user else _DUMMY_HASH)
    if not user or not ok or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return create_access_token(str(user.id))


def set_global_role(db: Session, actor: User, user_id: uuid.UUID, role: GlobalRole) -> User:
    if actor.id == user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own role")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.global_role = role
    db.commit()
    db.refresh(user)
    return user
