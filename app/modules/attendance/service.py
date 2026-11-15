"""Check-in: scanning tickets, per-session attendance, and the attendance report."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.common.enums import AttendanceMethod, ClubRole, EventStatus, RegistrationStatus
from app.core.deps import check_club_access
from app.modules.attendance.models import AttendanceRecord, Certificate
from app.modules.attendance.schemas import (AttendanceReport, AttendeeAttendance, ScanResult,
                                            SessionStat)
from app.modules.events.models import Event, EventSession
from app.modules.identity.models import User
from app.modules.registrations import service as registrations_service
from app.modules.registrations.models import Registration, Ticket

CHECKIN_OPENS_BEFORE = timedelta(minutes=30)   # automatic session pick: opens 30 min before start


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(code, msg)


# ---------------- shared rules ----------------
def percentage(attended: int, total: int) -> Decimal:
    return (Decimal(attended) * 100 / Decimal(total)).quantize(Decimal("0.01")) if total else Decimal("0.00")


def is_eligible(event: Event, attended: int, total: int) -> bool:
    """Certificate rule: enabled, at least one session attended, and the % threshold met."""
    return bool(event.certificate_enabled) and attended >= 1 and \
        percentage(attended, total) >= Decimal(event.certificate_min_attendance)


def get_event_with_sessions(db: Session, event_id: uuid.UUID) -> Event:
    event = db.scalar(select(Event).where(Event.id == event_id)
                      .options(selectinload(Event.sessions)))
    if not event:
        raise _err(status.HTTP_404_NOT_FOUND, "Event not found")
    return event


def _staff_event(db: Session, actor: User, event_id: uuid.UUID) -> Event:
    event = get_event_with_sessions(db, event_id)
    check_club_access(db, actor, event.club_id, ClubRole.COMMITTEE_LEADER)
    return event


def _pick_session(event: Event, session_id: uuid.UUID | None) -> EventSession:
    sessions = sorted(event.sessions, key=lambda s: s.start_time)
    if session_id:  # a leader choosing explicitly may check people in at any time
        chosen = next((s for s in sessions if s.id == session_id), None)
        if not chosen:
            raise _err(status.HTTP_404_NOT_FOUND, "That session doesn't belong to this event")
        return chosen
    now = datetime.now(timezone.utc)
    open_now = [s for s in sessions if s.start_time - CHECKIN_OPENS_BEFORE <= now <= s.end_time]
    if not open_now:
        raise _err(status.HTTP_409_CONFLICT,
                   "No session is open for check-in right now. Choose a session from the list.")
    return open_now[0]


def _record(db: Session, event: Event, session: EventSession, reg: Registration,
            ticket: Ticket, actor: User, method: AttendanceMethod) -> ScanResult:
    def existing():
        return db.scalar(select(AttendanceRecord).where(
            AttendanceRecord.session_id == session.id, AttendanceRecord.ticket_id == ticket.id))

    record, outcome = existing(), "already_checked_in"
    if record is None:
        record = AttendanceRecord(
            session_id=session.id, ticket_id=ticket.id, user_id=reg.user_id, event_id=event.id,
            scanned_by=actor.id, method=method, scanned_at=datetime.now(timezone.utc))
        db.add(record)
        try:
            db.commit()
            outcome = "checked_in"
        except IntegrityError:   # two scanners hit the same ticket at once: second one is a repeat
            db.rollback()
            record = existing()
    holder = db.get(User, reg.user_id)
    return ScanResult(result=outcome, attendee_name=holder.full_name, student_id=holder.student_id,
                      session_id=session.id, session_title=session.title,
                      scanned_at=record.scanned_at)


def _require_checkin_open(event: Event) -> None:
    if event.status not in (EventStatus.PUBLISHED, EventStatus.COMPLETED):
        raise _err(status.HTTP_409_CONFLICT, f"Check-in isn't available: the event is {event.status.value}")


# ---------------- check-in ----------------
def check_in_by_qr(db: Session, actor: User, event_id: uuid.UUID, payload: str,
                   session_id: uuid.UUID | None) -> ScanResult:
    event = _staff_event(db, actor, event_id)
    _require_checkin_open(event)

    code = registrations_service.parse_qr_payload(payload)   # rejects forged codes, no DB needed
    if not code:
        raise _err(status.HTTP_400_BAD_REQUEST, "That isn't a valid ticket QR code")
    ticket = db.scalar(select(Ticket).where(Ticket.ticket_code == code)
                       .options(selectinload(Ticket.registration)))
    if not ticket:
        raise _err(status.HTTP_404_NOT_FOUND, "Ticket not found")
    reg = ticket.registration
    if reg.event_id != event.id:
        raise _err(status.HTTP_409_CONFLICT, "This ticket is for a different event")
    if not ticket.is_valid or reg.status != RegistrationStatus.CONFIRMED:
        raise _err(status.HTTP_409_CONFLICT, "This ticket is no longer valid")
    return _record(db, event, _pick_session(event, session_id), reg, ticket, actor,
                   AttendanceMethod.QR_SCAN)


def check_in_manual(db: Session, actor: User, event_id: uuid.UUID, registration_id: uuid.UUID,
                    session_id: uuid.UUID | None) -> ScanResult:
    event = _staff_event(db, actor, event_id)
    _require_checkin_open(event)
    reg = db.scalar(select(Registration).where(Registration.id == registration_id)
                    .options(selectinload(Registration.ticket)))
    if not reg or reg.event_id != event.id:
        raise _err(status.HTTP_404_NOT_FOUND, "Registration not found for this event")
    if reg.status != RegistrationStatus.CONFIRMED or reg.ticket is None or not reg.ticket.is_valid:
        raise _err(status.HTTP_409_CONFLICT, "Only confirmed registrations can be checked in")
    return _record(db, event, _pick_session(event, session_id), reg, reg.ticket, actor,
                   AttendanceMethod.MANUAL)


# ---------------- report ----------------
def attendance_report(db: Session, actor: User, event_id: uuid.UUID) -> AttendanceReport:
    event = _staff_event(db, actor, event_id)
    sessions = sorted(event.sessions, key=lambda s: s.start_time)
    total = len(sessions)

    attended: dict[uuid.UUID, set[uuid.UUID]] = {}
    for user_id, session_id in db.execute(
            select(AttendanceRecord.user_id, AttendanceRecord.session_id)
            .where(AttendanceRecord.event_id == event_id)).all():
        attended.setdefault(user_id, set()).add(session_id)
    issued = set(db.scalars(select(Certificate.user_id).where(Certificate.event_id == event_id)))

    rows = db.execute(
        select(Registration, User).join(User, User.id == Registration.user_id)
        .where(Registration.event_id == event_id,
               Registration.status == RegistrationStatus.CONFIRMED)
        .order_by(User.full_name)).all()

    attendees = []
    for reg, user in rows:
        done = attended.get(user.id, set())
        attendees.append(AttendeeAttendance(
            registration_id=reg.id, user_id=user.id, full_name=user.full_name, email=user.email,
            student_id=user.student_id, attended_session_ids=sorted(done, key=str),
            sessions_attended=len(done), total_sessions=total,
            percentage=float(percentage(len(done), total)),
            eligible=is_eligible(event, len(done), total), certificate_issued=user.id in issued))

    return AttendanceReport(
        event_id=event.id, event_title=event.title, event_status=event.status,
        certificate_enabled=event.certificate_enabled,
        required_percentage=float(event.certificate_min_attendance),
        registered_total=len(attendees),
        checked_in_total=sum(1 for a in attendees if a.sessions_attended > 0),
        sessions=[SessionStat(id=s.id, title=s.title, start_time=s.start_time, end_time=s.end_time,
                              checked_in=sum(1 for a in attendees if s.id in a.attended_session_ids))
                  for s in sessions],
        attendees=attendees)
