import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.common.enums import (BookingStatus, ClubStatus, EventCategory, EventStatus,
                              RegistrationStatus, ResourceType)
from app.modules.clubs.models import Club
from app.modules.events.models import Event, EventSession
from app.modules.events.schemas import (EventCreate, EventRead, EventSummary, EventUpdate,
                                        SessionCreate)
from app.modules.identity.models import User
from app.modules.attendance import certificates as certificates_service
from app.modules.registrations import service as registrations_service
from app.modules.registrations.models import Registration
from app.modules.resources import service as resources_service
from app.modules.resources.models import Resource, ResourceBooking

SCHEDULE_FIELDS = {"start_time", "end_time", "venue_id"}
NON_NULLABLE = {"title", "category", "capacity", "certificate_enabled",
                "certificate_min_attendance", "start_time", "end_time"}


def _bad(msg: str, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(code, msg)


# ---------------- helpers ----------------
def get_event_or_404(db: Session, event_id: uuid.UUID) -> Event:
    event = db.scalar(
        select(Event).where(Event.id == event_id).options(selectinload(Event.sessions))
    )
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return event


def confirmed_count(db: Session, event_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count(Registration.id)).where(
            Registration.event_id == event_id,
            Registration.status == RegistrationStatus.CONFIRMED,
        )
    )


def to_read(db: Session, event: Event) -> EventRead:
    n = confirmed_count(db, event.id)
    return EventRead.model_validate(event).model_copy(
        update={"registered_count": n, "seats_left": max(event.capacity - n, 0)}
    )


def _validate_schedule(start: datetime, end: datetime, deadline: datetime | None) -> None:
    if end <= start:
        raise _bad("end_time must be after start_time")
    if deadline and deadline > start:
        raise _bad("registration_deadline must be before the event starts")


def _validate_venue(db: Session, venue_id: uuid.UUID, capacity: int) -> Resource:
    venue = db.get(Resource, venue_id)
    if not venue or not venue.is_active or venue.resource_type != ResourceType.VENUE:
        raise _bad("venue_id must refer to an active venue")
    if venue.capacity is not None and capacity > venue.capacity:
        raise _bad(f"Event capacity ({capacity}) exceeds venue capacity ({venue.capacity})")
    return venue


def _check_in_window(s_start: datetime, s_end: datetime, start: datetime, end: datetime) -> None:
    if s_start < start or s_end > end:
        raise _bad("Sessions must fall within the event's start and end time")


def _active_bookings(db: Session, event_id: uuid.UUID) -> list[ResourceBooking]:
    return list(db.scalars(
        select(ResourceBooking).where(
            ResourceBooking.event_id == event_id,
            ResourceBooking.status.in_(resources_service.ACTIVE_STATUSES),
        )
    ).all())


# ---------------- create / update ----------------
def create_event(db: Session, user: User, data: EventCreate) -> EventRead:
    club = db.get(Club, data.club_id)
    if not club:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Club not found")
    if club.status != ClubStatus.ACTIVE:
        raise _bad("This club is not active", status.HTTP_409_CONFLICT)
    if data.start_time <= datetime.now(timezone.utc):
        raise _bad("start_time must be in the future")
    if data.venue_id:
        _validate_venue(db, data.venue_id, data.capacity)

    event = Event(
        club_id=data.club_id, created_by=user.id, venue_id=data.venue_id,
        title=data.title, description=data.description, category=data.category,
        banner_url=data.banner_url, start_time=data.start_time, end_time=data.end_time,
        registration_deadline=data.registration_deadline, capacity=data.capacity,
        certificate_enabled=data.certificate_enabled,
        certificate_min_attendance=data.certificate_min_attendance,
        status=EventStatus.DRAFT,
    )
    if data.sessions:
        for s in data.sessions:
            _check_in_window(s.start_time, s.end_time, data.start_time, data.end_time)
        event.sessions = [EventSession(title=s.title, start_time=s.start_time, end_time=s.end_time)
                          for s in data.sessions]
    else:
        event.sessions = [EventSession(title="Main Session",
                                       start_time=data.start_time, end_time=data.end_time)]
    db.add(event)
    db.flush()

    if data.venue_id:  # request the venue in the SAME transaction: both succeed or neither does
        resources_service.create_booking(
            db, resource_id=data.venue_id, requested_by=user.id, start=data.start_time,
            end=data.end_time, event_id=event.id, notes=f"Venue for: {event.title}", commit=False,
        )
    db.commit()
    return to_read(db, event)


def update_event(db: Session, user: User, event: Event, data: EventUpdate) -> EventRead:
    if event.status in (EventStatus.CANCELLED, EventStatus.COMPLETED):
        raise _bad(f"A {event.status.value} event cannot be edited", status.HTTP_409_CONFLICT)

    changes = data.model_dump(exclude_unset=True)
    for key in NON_NULLABLE & changes.keys():
        if changes[key] is None:
            raise _bad(f"{key} cannot be null")

    if SCHEDULE_FIELDS & changes.keys() and event.status != EventStatus.DRAFT:
        raise _bad("Time and venue can only be changed while the event is a draft",
                   status.HTTP_409_CONFLICT)

    new_start = changes.get("start_time", event.start_time)
    new_end = changes.get("end_time", event.end_time)
    new_deadline = changes.get("registration_deadline", event.registration_deadline)
    new_capacity = changes.get("capacity", event.capacity)
    new_venue = changes["venue_id"] if "venue_id" in changes else event.venue_id
    _validate_schedule(new_start, new_end, new_deadline)

    if new_capacity < confirmed_count(db, event.id):
        raise _bad("Capacity cannot be lower than the number of confirmed registrations",
                   status.HTTP_409_CONFLICT)
    if new_venue:
        _validate_venue(db, new_venue, new_capacity)

    reschedule = (new_start, new_end, new_venue) != (event.start_time, event.end_time, event.venue_id)
    if reschedule:
        old = next((b for b in _active_bookings(db, event.id)
                    if b.resource_id == event.venue_id), None)
        others = [b for b in _active_bookings(db, event.id) if not (old and b.id == old.id)]
        if others:
            raise _bad("Cancel this event's equipment bookings before rescheduling",
                       status.HTTP_409_CONFLICT)
        if len(event.sessions) == 1:
            event.sessions[0].start_time, event.sessions[0].end_time = new_start, new_end
        else:
            for s in event.sessions:
                _check_in_window(s.start_time, s.end_time, new_start, new_end)
        if old:
            old.status = BookingStatus.CANCELLED
            db.flush()  # free the slot before re-booking (the same event may keep the same venue)

    for key, value in changes.items():
        setattr(event, key, value)

    if reschedule and new_venue:
        resources_service.create_booking(
            db, resource_id=new_venue, requested_by=user.id, start=new_start, end=new_end,
            event_id=event.id, notes=f"Venue for: {event.title}", commit=False,
        )
    if "capacity" in changes and event.status == EventStatus.PUBLISHED:
        db.flush()
        registrations_service.promote_waitlist(db, event)  # more seats -> waitlist moves up
    db.commit()
    return to_read(db, event)


# ---------------- lifecycle ----------------
def publish_event(db: Session, event: Event) -> EventRead:
    if event.status != EventStatus.DRAFT:
        raise _bad("Only draft events can be published", status.HTTP_409_CONFLICT)
    if event.start_time <= datetime.now(timezone.utc):
        raise _bad("The event start time has already passed")
    if event.venue_id:
        approved = any(b.resource_id == event.venue_id and b.status == BookingStatus.APPROVED
                       for b in _active_bookings(db, event.id))
        if not approved:
            raise _bad("The venue booking must be approved by an administrator first",
                       status.HTTP_409_CONFLICT)
    event.status = EventStatus.PUBLISHED
    db.commit()
    return to_read(db, event)


def cancel_event(db: Session, event: Event) -> EventRead:
    if event.status in (EventStatus.CANCELLED, EventStatus.COMPLETED):
        raise _bad(f"Event is already {event.status.value}", status.HTTP_409_CONFLICT)
    event.status = EventStatus.CANCELLED
    resources_service.cancel_bookings_for_event(db, event.id)  # frees venue + equipment
    registrations_service.invalidate_event_tickets(db, event.id)  # QR codes stop working
    db.commit()
    return to_read(db, event)


def complete_event(db: Session, event: Event) -> EventRead:
    if event.status != EventStatus.PUBLISHED:
        raise _bad("Only published events can be completed", status.HTTP_409_CONFLICT)
    if datetime.now(timezone.utc) < event.end_time:
        raise _bad("The event has not ended yet", status.HTTP_409_CONFLICT)
    event.status = EventStatus.COMPLETED
    certificates_service.issue_certificates_for_event(db, event)  # eligible attendees get one
    db.commit()
    return to_read(db, event)


# ---------------- sessions ----------------
def add_session(db: Session, event: Event, data: SessionCreate) -> EventRead:
    if event.status != EventStatus.DRAFT:
        raise _bad("Sessions can only be changed while the event is a draft", status.HTTP_409_CONFLICT)
    _check_in_window(data.start_time, data.end_time, event.start_time, event.end_time)
    event.sessions.append(EventSession(title=data.title, start_time=data.start_time,
                                       end_time=data.end_time))
    db.commit()
    db.refresh(event)
    return to_read(db, event)


def delete_session(db: Session, event: Event, session_id: uuid.UUID) -> EventRead:
    if event.status != EventStatus.DRAFT:
        raise _bad("Sessions can only be changed while the event is a draft", status.HTTP_409_CONFLICT)
    session = next((s for s in event.sessions if s.id == session_id), None)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if len(event.sessions) == 1:
        raise _bad("An event needs at least one session", status.HTTP_409_CONFLICT)
    event.sessions.remove(session)
    db.commit()
    db.refresh(event)
    return to_read(db, event)


# ---------------- browsing ----------------
def list_events(
    db: Session, *, statuses: list[EventStatus] | None, club_id: uuid.UUID | None = None,
    q: str | None = None, category: EventCategory | None = None, upcoming: bool = False,
    limit: int = 20, offset: int = 0,
) -> list[EventSummary]:
    registered = (
        select(func.count(Registration.id))
        .where(Registration.event_id == Event.id,
               Registration.status == RegistrationStatus.CONFIRMED)
        .correlate(Event).scalar_subquery()
    )
    stmt = select(Event, registered.label("registered_count"))
    if statuses:
        stmt = stmt.where(Event.status.in_(statuses))
    if club_id:
        stmt = stmt.where(Event.club_id == club_id)
    if category:
        stmt = stmt.where(Event.category == category)
    if q:
        stmt = stmt.where(Event.title.ilike(f"%{q}%"))
    if upcoming:
        stmt = stmt.where(Event.end_time > datetime.now(timezone.utc))
    stmt = stmt.order_by(Event.start_time).limit(limit).offset(offset)

    return [
        EventSummary.model_validate(e).model_copy(
            update={"registered_count": n, "seats_left": max(e.capacity - n, 0)})
        for e, n in db.execute(stmt).all()
    ]
