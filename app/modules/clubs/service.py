import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import ClubRole
from app.modules.clubs.models import Club, Membership
from app.modules.clubs.schemas import ClubCreate, MyClubRead
from app.modules.identity.models import User


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def create_club(db: Session, data: ClubCreate) -> Club:
    if not db.get(User, data.president_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "President user not found")
    slug = _slugify(data.name)
    if db.scalar(select(Club).where((Club.name == data.name) | (Club.slug == slug))):
        raise HTTPException(status.HTTP_409_CONFLICT, "A club with this name already exists")

    club = Club(name=data.name, slug=slug, description=data.description, category=data.category)
    club.memberships.append(Membership(user_id=data.president_id, role=ClubRole.PRESIDENT))
    db.add(club)
    db.commit()
    db.refresh(club)
    return club


def set_member_role(
    db: Session, club_id: uuid.UUID, user_id: uuid.UUID, role: ClubRole, actor: User
) -> Membership:
    m = db.scalar(
        select(Membership).where(Membership.club_id == club_id, Membership.user_id == user_id)
    )
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership not found")
    if m.user_id == actor.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own club role")
    m.role = role
    db.commit()
    db.refresh(m)
    return m


def list_my_clubs(db: Session, user: User) -> list[MyClubRead]:
    rows = db.execute(
        select(Membership, Club)
        .join(Club, Club.id == Membership.club_id)
        .where(Membership.user_id == user.id, Membership.is_active.is_(True))
        .order_by(Club.name)
    ).all()
    return [
        MyClubRead(club_id=c.id, club_name=c.name, club_slug=c.slug, role=m.role)
        for m, c in rows
    ]
