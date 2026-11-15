"""Authentication + RBAC dependencies.

Usage in routers:
    CurrentUser                                   -> any logged-in user
    Depends(require_admin)                        -> system admins only
    Depends(require_club_role(ClubRole.PRESIDENT))-> route must have a {club_id} path param
"""
import uuid
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from app.common.enums import ClubRole, GlobalRole
from app.core.config import settings
from app.core.database import DbSession
from app.core.security import decode_access_token
from app.modules.clubs.models import Membership
from app.modules.identity.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")


def _unauthorized(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: DbSession
) -> User:
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _unauthorized()

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ---------- Global (platform-wide) roles ----------
def require_global_roles(*roles: GlobalRole):
    def checker(user: CurrentUser) -> User:
        if user.global_role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return checker


require_admin = require_global_roles(GlobalRole.SYSTEM_ADMIN)


# ---------- Club-scoped roles ----------
@dataclass
class ClubAccess:
    user: User
    club_id: uuid.UUID
    role: ClubRole | None  # None => system admin acting without a membership


def check_club_access(
    db, user: User, club_id: uuid.UUID, min_role: ClubRole
) -> ClubAccess:
    """Reusable by services too (e.g. events module derives club_id from the event,
    then calls this)."""
    if user.global_role == GlobalRole.SYSTEM_ADMIN:
        return ClubAccess(user, club_id, None)

    membership = db.scalar(
        select(Membership).where(
            Membership.club_id == club_id,
            Membership.user_id == user.id,
            Membership.is_active.is_(True),
        )
    )
    if membership is None or not membership.role.at_least(min_role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"Requires club role '{min_role.value}' or higher"
        )
    return ClubAccess(user, club_id, membership.role)


def require_club_role(min_role: ClubRole):
    def checker(club_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ClubAccess:
        return check_club_access(db, user, club_id, min_role)

    return checker


# ---------- Optional authentication (public endpoints that personalise when logged in) ----------
oauth2_optional = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login", auto_error=False)


def get_optional_user(
    token: Annotated[str | None, Depends(oauth2_optional)], db: DbSession
) -> User | None:
    if not token:
        return None
    return get_current_user(token, db)  # a present-but-invalid token is still a 401


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
