import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.common.enums import ClubRole
from app.core.database import DbSession
from app.core.deps import ClubAccess, CurrentUser, require_admin, require_club_role
from app.modules.clubs import service
from app.modules.clubs.models import Club
from app.modules.clubs.schemas import (ClubCreate, ClubRead, MemberRead, MemberRoleUpdate,
                                       MyClubRead)

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("", response_model=list[ClubRead])
def list_clubs(db: DbSession):
    """Public club directory."""
    return db.scalars(select(Club).order_by(Club.name)).all()


@router.get("/mine", response_model=list[MyClubRead])
def my_clubs(db: DbSession, user: CurrentUser):
    """Clubs the logged-in user belongs to, with their role in each."""
    return service.list_my_clubs(db, user)


@router.post(
    "",
    response_model=ClubRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_club(data: ClubCreate, db: DbSession):
    return service.create_club(db, data)


@router.patch("/{club_id}/members/{user_id}/role", response_model=MemberRead)
def update_member_role(
    club_id: uuid.UUID,
    user_id: uuid.UUID,
    body: MemberRoleUpdate,
    db: DbSession,
    access: Annotated[ClubAccess, Depends(require_club_role(ClubRole.PRESIDENT))],
):
    """President (or system admin) only."""
    return service.set_member_role(db, club_id, user_id, body.role, access.user)
