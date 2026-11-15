import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.common.enums import ClubRole, EventCategory, EventStatus
from app.core.database import DbSession
from app.core.deps import (ClubAccess, CurrentUser, OptionalUser, check_club_access,
                           require_club_role)
from app.modules.events import service
from app.modules.events.models import Event
from app.modules.events.schemas import (EventCreate, EventRead, EventSummary, EventUpdate,
                                        SessionCreate)

router = APIRouter(tags=["events"])


def _manage(db, user, event: Event) -> Event:
    """Committee leaders and above of the event's club (or a system admin)."""
    check_club_access(db, user, event.club_id, ClubRole.COMMITTEE_LEADER)
    return event


# ----- public browsing -----
@router.get("/events", response_model=list[EventSummary])
def browse_events(
    db: DbSession,
    q: str | None = Query(None, max_length=100, description="Search in title"),
    category: EventCategory | None = None,
    club_id: uuid.UUID | None = None,
    upcoming: bool = True,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Published events only, soonest first, with seats_left."""
    return service.list_events(db, statuses=[EventStatus.PUBLISHED], club_id=club_id, q=q,
                               category=category, upcoming=upcoming, limit=limit, offset=offset)


@router.get("/events/{event_id}", response_model=EventRead)
def get_event(event_id: uuid.UUID, db: DbSession, user: OptionalUser):
    event = service.get_event_or_404(db, event_id)
    if event.status == EventStatus.DRAFT:
        # Drafts are invisible to the public: answer 404, not 403, so their existence isn't leaked.
        try:
            if user is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
            _manage(db, user, event)
        except HTTPException:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return service.to_read(db, event)


# ----- club management view (includes drafts) -----
@router.get("/clubs/{club_id}/events", response_model=list[EventSummary])
def club_events(
    club_id: uuid.UUID,
    db: DbSession,
    _: Annotated[ClubAccess, Depends(require_club_role(ClubRole.COMMITTEE_LEADER))],
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return service.list_events(db, statuses=None, club_id=club_id, limit=limit, offset=offset)


# ----- create / edit -----
@router.post("/events", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def create_event(data: EventCreate, db: DbSession, user: CurrentUser):
    # club_id is in the body here (not the path), so call the check directly.
    check_club_access(db, user, data.club_id, ClubRole.COMMITTEE_LEADER)
    return service.create_event(db, user, data)


@router.patch("/events/{event_id}", response_model=EventRead)
def update_event(event_id: uuid.UUID, data: EventUpdate, db: DbSession, user: CurrentUser):
    event = _manage(db, user, service.get_event_or_404(db, event_id))
    return service.update_event(db, user, event, data)


@router.post("/events/{event_id}/publish", response_model=EventRead)
def publish_event(event_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return service.publish_event(db, _manage(db, user, service.get_event_or_404(db, event_id)))


@router.post("/events/{event_id}/cancel", response_model=EventRead)
def cancel_event(event_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return service.cancel_event(db, _manage(db, user, service.get_event_or_404(db, event_id)))


@router.post("/events/{event_id}/complete", response_model=EventRead)
def complete_event(event_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return service.complete_event(db, _manage(db, user, service.get_event_or_404(db, event_id)))


# ----- sessions -----
@router.post("/events/{event_id}/sessions", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def add_session(event_id: uuid.UUID, data: SessionCreate, db: DbSession, user: CurrentUser):
    return service.add_session(db, _manage(db, user, service.get_event_or_404(db, event_id)), data)


@router.delete("/events/{event_id}/sessions/{session_id}", response_model=EventRead)
def delete_session(event_id: uuid.UUID, session_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return service.delete_session(
        db, _manage(db, user, service.get_event_or_404(db, event_id)), session_id)
