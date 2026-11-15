import base64
import hmac
import io
import secrets
import uuid
from datetime import datetime, timezone

import qrcode
from fastapi import HTTPException, status
from qrcode.constants import ERROR_CORRECT_M
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.common.enums import ClubRole, EventStatus, RegistrationStatus
from app.core.deps import check_club_access
from app.core.security import sign_value
from app.modules.events.models import Event
from app.modules.identity.models import User
from app.modules.registrations.models import Registration, Ticket
from app.modules.registrations.schemas import (AttendeeRead, MyRegistration, RegistrationRead,
                                               TicketRead)
from app.modules.resources.models import Resource

QR_PREFIX = "CEMF1"
SIG_LEN = 32  # hex chars of the HMAC kept in the QR (128 bits)


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(code, msg)


# ---------------- QR payload (the attendance scanner reuses parse_qr_payload) ----------------
def _signature(ticket_code: str) -> str:
    return sign_value(ticket_code)[:SIG_LEN]


def build_qr_payload(ticket: Ticket) -> str:
    return f"{QR_PREFIX}:{ticket.ticket_code}:{ticket.signature}"


def parse_qr_payload(payload: str) -> str | None:
    """Returns the ticket_code if the payload is well-formed and correctly signed, else None.
    Rejects forged codes without touching the database."""
    parts = payload.strip().split(":")
    if len(parts) != 3 or parts[0] != QR_PREFIX:
        return None
    code, sig = parts[1], parts[2]
    return code if hmac.compare_digest(_signature(code), sig) else None


def render_qr_data_url(payload: str) -> str:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------- internals ----------------
def confirmed_count(db: Session, event_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count(Registration.id)).where(
            Registration.event_id == event_id,
            Registration.status == RegistrationStatus.CONFIRMED,
        )
    )


def _issue_ticket(reg: Registration) -> None:
    """Create (or re-issue after a cancellation) the single ticket for a registration."""
    code = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    if reg.ticket is None:
        reg.ticket = Ticket(ticket_code=code, signature=_signature(code), issued_at=now)
    else:  # re-issue with a fresh code so the old QR can never come back to life
        reg.ticket.ticket_code = code
        reg.ticket.signature = _signature(code)
        reg.ticket.is_valid = True
        reg.ticket.issued_at = now


def _queue_position(db: Session, reg: Registration) -> int | None:
    if reg.status != RegistrationStatus.WAITLISTED:
        return None
    return db.scalar(
        select(func.count(Registration.id)).where(
            Registration.event_id == reg.event_id,
            Registration.status == RegistrationStatus.WAITLISTED,
            Registration.registered_at <= reg.registered_at,
        )
    )


def to_read(db: Session, reg: Registration) -> RegistrationRead:
    return RegistrationRead(
        id=reg.id, event_id=reg.event_id, user_id=reg.user_id, status=reg.status,
        registered_at=reg.registered_at, cancelled_at=reg.cancelled_at,
        queue_position=_queue_position(db, reg),
    )


def _lock_event(db: Session, event_id: uuid.UUID) -> Event:
    """Row lock: concurrent registrations for one event queue up, so two students can't
    both take the last seat."""
    event = db.scalar(select(Event).where(Event.id == event_id).with_for_update())
    if not event:
        raise _err(status.HTTP_404_NOT_FOUND, "Event not found")
    return event


def promote_waitlist(db: Session, event: Event) -> int:
    """Fill free seats from the waitlist, oldest first. Caller must have flushed pending
    status changes (the session runs with autoflush off). Caller commits."""
    free = event.capacity - confirmed_count(db, event.id)
    if free <= 0:
        return 0
    waiting = db.scalars(
        select(Registration)
        .where(Registration.event_id == event.id,
               Registration.status == RegistrationStatus.WAITLISTED)
        .order_by(Registration.registered_at)
        .limit(free)
    ).all()
    for reg in waiting:
        reg.status = RegistrationStatus.CONFIRMED
        _issue_ticket(reg)
    db.flush()
    return len(waiting)


def invalidate_event_tickets(db: Session, event_id: uuid.UUID) -> None:
    """Used when an event is cancelled. No commit: the caller owns the transaction."""
    db.execute(
        update(Ticket)
        .where(Ticket.registration_id.in_(
            select(Registration.id).where(Registration.event_id == event_id)))
        .values(is_valid=False)
    )


# ---------------- student actions ----------------
def register(db: Session, user: User, event_id: uuid.UUID) -> RegistrationRead:
    event = _lock_event(db, event_id)
    now = datetime.now(timezone.utc)
    if event.status != EventStatus.PUBLISHED:
        raise _err(status.HTTP_409_CONFLICT, "This event isn't open for registration")
    if now >= (event.registration_deadline or event.start_time):
        raise _err(status.HTTP_409_CONFLICT, "Registration for this event has closed")

    reg = db.scalar(select(Registration).where(
        Registration.event_id == event_id, Registration.user_id == user.id))
    if reg and reg.status != RegistrationStatus.CANCELLED:
        raise _err(status.HTTP_409_CONFLICT, "You're already registered for this event")

    new_status = (RegistrationStatus.CONFIRMED
                  if confirmed_count(db, event_id) < event.capacity
                  else RegistrationStatus.WAITLISTED)
    if reg:  # re-registering after a cancellation: joins the back of the queue
        reg.status, reg.cancelled_at, reg.registered_at = new_status, None, now
    else:
        reg = Registration(event_id=event_id, user_id=user.id, status=new_status, registered_at=now)
        db.add(reg)
    db.flush()
    if new_status == RegistrationStatus.CONFIRMED:
        _issue_ticket(reg)
    db.commit()
    return to_read(db, reg)


def cancel_registration(db: Session, user: User, event_id: uuid.UUID) -> RegistrationRead:
    event = _lock_event(db, event_id)
    reg = db.scalar(select(Registration).where(
        Registration.event_id == event_id, Registration.user_id == user.id))
    if not reg or reg.status == RegistrationStatus.CANCELLED:
        raise _err(status.HTTP_404_NOT_FOUND, "You aren't registered for this event")
    if datetime.now(timezone.utc) >= event.start_time:
        raise _err(status.HTTP_409_CONFLICT, "You can't cancel after the event has started")

    was_confirmed = reg.status == RegistrationStatus.CONFIRMED
    reg.status = RegistrationStatus.CANCELLED
    reg.cancelled_at = datetime.now(timezone.utc)
    if reg.ticket:
        reg.ticket.is_valid = False
    db.flush()
    if was_confirmed and event.status == EventStatus.PUBLISHED:
        promote_waitlist(db, event)
    db.commit()
    return to_read(db, reg)


def get_my_registration(db: Session, user: User, event_id: uuid.UUID) -> RegistrationRead | None:
    reg = db.scalar(select(Registration).where(
        Registration.event_id == event_id, Registration.user_id == user.id))
    if not reg or reg.status == RegistrationStatus.CANCELLED:
        return None
    return to_read(db, reg)


def list_my_registrations(db: Session, user: User) -> list[MyRegistration]:
    rows = db.execute(
        select(Registration, Event)
        .join(Event, Event.id == Registration.event_id)
        .where(Registration.user_id == user.id,
               Registration.status != RegistrationStatus.CANCELLED)
        .order_by(Event.start_time)
    ).all()
    return [
        MyRegistration(**to_read(db, r).model_dump(), event_title=e.title,
                       event_start_time=e.start_time, event_end_time=e.end_time,
                       event_status=e.status)
        for r, e in rows
    ]


# ---------------- tickets ----------------
def get_ticket(db: Session, user: User, registration_id: uuid.UUID) -> TicketRead:
    reg = db.scalar(select(Registration).where(Registration.id == registration_id)
                    .options(selectinload(Registration.ticket)))
    if not reg:
        raise _err(status.HTTP_404_NOT_FOUND, "Ticket not found")
    event = db.get(Event, reg.event_id)
    if reg.user_id != user.id:  # not the holder: only that club's leaders (or admins) may look
        check_club_access(db, user, event.club_id, ClubRole.COMMITTEE_LEADER)
    if reg.status != RegistrationStatus.CONFIRMED or reg.ticket is None:
        raise _err(status.HTTP_404_NOT_FOUND, "There's no ticket for this registration")

    holder = db.get(User, reg.user_id)
    venue = db.get(Resource, event.venue_id) if event.venue_id else None
    payload = build_qr_payload(reg.ticket)
    return TicketRead(
        id=reg.ticket.id, registration_id=reg.id, event_id=event.id, event_title=event.title,
        event_start_time=event.start_time, event_end_time=event.end_time,
        venue_name=venue.name if venue else None,
        holder_name=holder.full_name, student_id=holder.student_id,
        ticket_code=reg.ticket.ticket_code,
        is_valid=reg.ticket.is_valid and event.status != EventStatus.CANCELLED,
        issued_at=reg.ticket.issued_at, qr_payload=payload, qr_image=render_qr_data_url(payload),
    )


# ---------------- organiser view ----------------
def list_attendees(db: Session, user: User, event_id: uuid.UUID,
                   status_filter: RegistrationStatus | None) -> list[AttendeeRead]:
    event = db.get(Event, event_id)
    if not event:
        raise _err(status.HTTP_404_NOT_FOUND, "Event not found")
    check_club_access(db, user, event.club_id, ClubRole.COMMITTEE_LEADER)
    stmt = (select(Registration, User)
            .join(User, User.id == Registration.user_id)
            .where(Registration.event_id == event_id)
            .order_by(Registration.registered_at))
    stmt = stmt.where(Registration.status == status_filter) if status_filter else \
        stmt.where(Registration.status != RegistrationStatus.CANCELLED)
    return [
        AttendeeRead(registration_id=r.id, user_id=u.id, full_name=u.full_name, email=u.email,
                     student_id=u.student_id, status=r.status, registered_at=r.registered_at)
        for r, u in db.execute(stmt).all()
    ]
