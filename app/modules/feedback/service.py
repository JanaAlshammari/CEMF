import csv
import io
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import ClubRole, EventStatus, RegistrationStatus
from app.core.deps import check_club_access
from app.modules.attendance.models import AttendanceRecord
from app.modules.events.models import Event
from app.modules.feedback.models import Feedback
from app.modules.feedback.schemas import (ClubFeedbackSummary, EventFeedbackRow, FeedbackComment,
                                          FeedbackCreate, FeedbackRead, FeedbackReport,
                                          FeedbackStatus, RatingAverages)
from app.modules.identity.models import User
from app.modules.registrations.models import Registration


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(code, msg)


def _event(db: Session, event_id: uuid.UUID) -> Event:
    event = db.get(Event, event_id)
    if not event:
        raise _err(status.HTTP_404_NOT_FOUND, "Event not found")
    return event


def _event_over(event: Event) -> bool:
    return event.status == EventStatus.COMPLETED or (
        event.status == EventStatus.PUBLISHED and datetime.now(timezone.utc) >= event.end_time)


def _eligibility(db: Session, user: User, event: Event) -> tuple[bool, str | None]:
    """Only people who actually attended may rate, and only once the event is over."""
    if event.status == EventStatus.CANCELLED:
        return False, "This event was cancelled"
    if not _event_over(event):
        return False, "Feedback opens when the event ends"
    attended = db.scalar(select(func.count(AttendanceRecord.id)).where(
        AttendanceRecord.event_id == event.id, AttendanceRecord.user_id == user.id))
    if not attended:
        return False, "Only people who attended can leave feedback"
    return True, None


def _mine(db: Session, user: User, event_id: uuid.UUID) -> Feedback | None:
    return db.scalar(select(Feedback).where(
        Feedback.event_id == event_id, Feedback.user_id == user.id))


# ---------------- student side ----------------
def feedback_status(db: Session, user: User, event_id: uuid.UUID) -> FeedbackStatus:
    event = _event(db, event_id)
    ok, reason = _eligibility(db, user, event)
    mine = _mine(db, user, event_id)
    return FeedbackStatus(can_submit=ok and mine is None, reason=reason,
                          submitted=FeedbackRead.model_validate(mine) if mine else None)


def save_feedback(db: Session, user: User, event_id: uuid.UUID, data: FeedbackCreate,
                  *, update: bool) -> FeedbackRead:
    event = _event(db, event_id)
    ok, reason = _eligibility(db, user, event)
    if not ok:
        raise _err(status.HTTP_409_CONFLICT, reason)
    fb = _mine(db, user, event_id)
    if update:
        if not fb:
            raise _err(status.HTTP_404_NOT_FOUND, "You haven't submitted feedback yet")
        for key, value in data.model_dump().items():
            setattr(fb, key, value)
    else:
        if fb:
            raise _err(status.HTTP_409_CONFLICT, "You've already sent feedback for this event")
        fb = Feedback(event_id=event_id, user_id=user.id, **data.model_dump())
        db.add(fb)
    db.commit()
    db.refresh(fb)
    return FeedbackRead.model_validate(fb)


# ---------------- organiser side ----------------
def _avg(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _pct(part: int, whole: int) -> float | None:
    return round(part * 100 / whole, 1) if whole else None


def _staff_event(db: Session, user: User, event_id: uuid.UUID) -> Event:
    event = _event(db, event_id)
    check_club_access(db, user, event.club_id, ClubRole.COMMITTEE_LEADER)
    return event


def _rows(db: Session, event_id: uuid.UUID):
    return db.execute(
        select(Feedback, User).join(User, User.id == Feedback.user_id)
        .where(Feedback.event_id == event_id).order_by(Feedback.created_at.desc())).all()


def feedback_report(db: Session, user: User, event_id: uuid.UUID) -> FeedbackReport:
    event = _staff_event(db, user, event_id)
    rows = _rows(db, event_id)
    fbs = [f for f, _ in rows]
    registered = db.scalar(select(func.count(Registration.id)).where(
        Registration.event_id == event_id, Registration.status == RegistrationStatus.CONFIRMED))
    attended = db.scalar(select(func.count(func.distinct(AttendanceRecord.user_id))).where(
        AttendanceRecord.event_id == event_id))
    col = lambda name: [getattr(f, name) for f in fbs if getattr(f, name) is not None]
    return FeedbackReport(
        event_id=event.id, event_title=event.title, event_status=event.status,
        registered_total=registered, attended_total=attended,
        attendance_rate=_pct(attended, registered),
        response_count=len(fbs), response_rate=_pct(len(fbs), attended),
        averages=RatingAverages(overall=_avg(col("overall_rating")), content=_avg(col("content_rating")),
                                organization=_avg(col("organization_rating")), venue=_avg(col("venue_rating"))),
        overall_distribution=[sum(1 for f in fbs if f.overall_rating == n) for n in range(1, 6)],
        comments=[FeedbackComment(author=None if f.is_anonymous else u.full_name,
                                  overall_rating=f.overall_rating, comments=f.comments,
                                  suggestions=f.suggestions, created_at=f.created_at)
                  for f, u in rows if f.comments or f.suggestions])


def _csv_safe(value) -> str:
    """Stops spreadsheet formula injection from free-text answers."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def feedback_csv(db: Session, user: User, event_id: uuid.UUID) -> tuple[str, str]:
    event = _staff_event(db, user, event_id)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Name", "Email", "Overall", "Content", "Organisation", "Venue",
                "Comments", "Suggestions", "Submitted (UTC)"])
    for f, u in _rows(db, event_id):
        w.writerow([_csv_safe("Anonymous" if f.is_anonymous else u.full_name),
                    "" if f.is_anonymous else _csv_safe(u.email),
                    f.overall_rating, f.content_rating or "", f.organization_rating or "",
                    f.venue_rating or "", _csv_safe(f.comments), _csv_safe(f.suggestions),
                    f.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")])
    return "\ufeff" + out.getvalue(), f"feedback-{event.id}.csv"   # BOM so Excel reads UTF-8


def club_summary(db: Session, club_id: uuid.UUID) -> ClubFeedbackSummary:
    """Caller has already checked the club role (route dependency)."""
    events = db.scalars(select(Event).where(Event.club_id == club_id, Event.status != EventStatus.DRAFT)
                        .order_by(Event.start_time.desc())).all()
    ids = [e.id for e in events]
    if not ids:
        return ClubFeedbackSummary(events=[], total_responses=0, average_overall=None)
    reg = dict(db.execute(select(Registration.event_id, func.count(Registration.id)).where(
        Registration.event_id.in_(ids), Registration.status == RegistrationStatus.CONFIRMED)
        .group_by(Registration.event_id)).all())
    att = dict(db.execute(select(AttendanceRecord.event_id, func.count(func.distinct(AttendanceRecord.user_id)))
                          .where(AttendanceRecord.event_id.in_(ids))
                          .group_by(AttendanceRecord.event_id)).all())
    fb = {eid: (n, float(a)) for eid, n, a in db.execute(
        select(Feedback.event_id, func.count(Feedback.id), func.avg(Feedback.overall_rating))
        .where(Feedback.event_id.in_(ids)).group_by(Feedback.event_id)).all()}
    rows = [EventFeedbackRow(event_id=e.id, title=e.title, start_time=e.start_time, status=e.status,
                             registered=reg.get(e.id, 0), attended=att.get(e.id, 0),
                             responses=fb.get(e.id, (0, 0))[0],
                             average_overall=round(fb[e.id][1], 2) if e.id in fb else None)
            for e in events]
    total = sum(n for n, _ in fb.values())
    weighted = sum(n * a for n, a in fb.values())
    return ClubFeedbackSummary(events=rows, total_responses=total,
                               average_overall=round(weighted / total, 2) if total else None)
