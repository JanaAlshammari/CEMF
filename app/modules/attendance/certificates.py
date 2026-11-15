"""Certificates: eligibility, issuing (automatic on event completion, or claimed by the
student), public verification, and PDF rendering."""
import base64
import io
import secrets
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import qrcode
from fastapi import HTTPException, status
from qrcode.constants import ERROR_CORRECT_M
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import ClubRole, EventStatus, RegistrationStatus
from app.core.config import settings
from app.core.deps import check_club_access
from app.modules.attendance.models import AttendanceRecord, Certificate
from app.modules.attendance.schemas import (CertificateDetail, CertificateRead, MyAttendance,
                                            VerifyResult)
from app.modules.attendance.service import (get_event_with_sessions, is_eligible, percentage)
from app.modules.clubs.models import Club
from app.modules.events.models import Event
from app.modules.identity.models import User
from app.modules.registrations.models import Registration


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(code, msg)


# ---------------- small helpers ----------------
def _tz():
    try:
        return ZoneInfo(settings.timezone_name)
    except Exception:           # tz database missing: fall back to UTC rather than crash
        return timezone.utc


def _date_text(start: datetime, end: datetime) -> str:
    s, e = start.astimezone(_tz()), end.astimezone(_tz())
    fmt = lambda d: f"{d.day} {d.strftime('%B %Y')}"
    return fmt(s) if s.date() == e.date() else f"{fmt(s)} to {fmt(e)}"


def _new_code() -> str:
    h = secrets.token_hex(8).upper()
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def _qr_png(text: str) -> bytes:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=6, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    return buf.getvalue()


def event_over(event: Event) -> bool:
    now = datetime.now(timezone.utc)
    return event.status == EventStatus.COMPLETED or \
        (event.status == EventStatus.PUBLISHED and now >= event.end_time)


def _attended_count(db: Session, event_id: uuid.UUID, user_id: uuid.UUID) -> int:
    return db.scalar(select(func.count(func.distinct(AttendanceRecord.session_id))).where(
        AttendanceRecord.event_id == event_id, AttendanceRecord.user_id == user_id))


def _create(db: Session, event: Event, user_id: uuid.UUID, attended: int) -> Certificate:
    cert = Certificate(event_id=event.id, user_id=user_id, verification_code=_new_code(),
                       attendance_percentage=percentage(attended, len(event.sessions)),
                       issued_at=datetime.now(timezone.utc))
    db.add(cert)
    db.flush()
    return cert


# ---------------- issuing ----------------
def issue_certificates_for_event(db: Session, event: Event) -> int:
    """Called when an event is marked completed: every eligible attendee gets a certificate.
    No commit: the caller owns the transaction."""
    if not event.certificate_enabled:
        return 0
    total = len(event.sessions)
    counts = db.execute(
        select(AttendanceRecord.user_id, func.count(func.distinct(AttendanceRecord.session_id)))
        .where(AttendanceRecord.event_id == event.id).group_by(AttendanceRecord.user_id)).all()
    have = set(db.scalars(select(Certificate.user_id).where(Certificate.event_id == event.id)))
    confirmed = set(db.scalars(select(Registration.user_id).where(
        Registration.event_id == event.id, Registration.status == RegistrationStatus.CONFIRMED)))
    issued = 0
    for user_id, attended in counts:
        if user_id in have or user_id not in confirmed or not is_eligible(event, attended, total):
            continue
        _create(db, event, user_id, attended)
        issued += 1
    return issued


def _existing(db: Session, event_id: uuid.UUID, user_id: uuid.UUID) -> Certificate | None:
    return db.scalar(select(Certificate).where(
        Certificate.event_id == event_id, Certificate.user_id == user_id))


def my_attendance(db: Session, user: User, event_id: uuid.UUID) -> MyAttendance:
    event = get_event_with_sessions(db, event_id)
    registered = db.scalar(select(Registration.id).where(
        Registration.event_id == event_id, Registration.user_id == user.id,
        Registration.status == RegistrationStatus.CONFIRMED))
    if not registered:
        raise _err(status.HTTP_404_NOT_FOUND, "You weren't registered for this event")
    total, attended = len(event.sessions), _attended_count(db, event_id, user.id)
    cert = _existing(db, event_id, user.id)
    return MyAttendance(
        event_id=event_id, sessions_attended=attended, total_sessions=total,
        percentage=float(percentage(attended, total)),
        required_percentage=float(event.certificate_min_attendance),
        certificate_enabled=event.certificate_enabled, event_over=event_over(event),
        eligible=is_eligible(event, attended, total), certificate_id=cert.id if cert else None)


def claim_certificate(db: Session, user: User, event_id: uuid.UUID, base_url: str) -> CertificateRead:
    event = get_event_with_sessions(db, event_id)
    cert = _existing(db, event_id, user.id)
    if cert is None:
        a = my_attendance(db, user, event_id)
        if not event.certificate_enabled:
            raise _err(status.HTTP_409_CONFLICT, "This event doesn't offer certificates")
        if not a.event_over:
            raise _err(status.HTTP_409_CONFLICT, "Certificates are available once the event has ended")
        if not a.eligible:
            raise _err(status.HTTP_409_CONFLICT,
                       f"You attended {a.percentage:g}% of sessions; {a.required_percentage:g}% is required")
        cert = _create(db, event, user.id, a.sessions_attended)
        db.commit()
    return _read(db, cert)


# ---------------- reading ----------------
def _read(db: Session, cert: Certificate) -> CertificateRead:
    event = db.get(Event, cert.event_id)
    club = db.get(Club, event.club_id)
    return CertificateRead(
        id=cert.id, event_id=event.id, event_title=event.title, club_name=club.name,
        event_start_time=event.start_time, event_end_time=event.end_time,
        date_text=_date_text(event.start_time, event.end_time),
        verification_code=cert.verification_code,
        attendance_percentage=float(cert.attendance_percentage), issued_at=cert.issued_at)


def list_my_certificates(db: Session, user: User) -> list[CertificateRead]:
    certs = db.scalars(select(Certificate).where(Certificate.user_id == user.id)
                       .order_by(Certificate.issued_at.desc())).all()
    return [_read(db, c) for c in certs]


def _load_for_viewer(db: Session, user: User, certificate_id: uuid.UUID) -> Certificate:
    cert = db.get(Certificate, certificate_id)
    if not cert:
        raise _err(status.HTTP_404_NOT_FOUND, "Certificate not found")
    if cert.user_id != user.id:     # not the holder: that club's leaders and admins only
        check_club_access(db, user, db.get(Event, cert.event_id).club_id, ClubRole.COMMITTEE_LEADER)
    return cert


def get_certificate(db: Session, user: User, certificate_id: uuid.UUID, base_url: str) -> CertificateDetail:
    cert = _load_for_viewer(db, user, certificate_id)
    holder = db.get(User, cert.user_id)
    verify_url = f"{base_url}/verify/{cert.verification_code}"
    qr = "data:image/png;base64," + base64.b64encode(_qr_png(verify_url)).decode()
    return CertificateDetail(**_read(db, cert).model_dump(), holder_name=holder.full_name,
                             student_id=holder.student_id, verify_url=verify_url, qr_image=qr)


def verify(db: Session, code: str) -> VerifyResult:
    cert = db.scalar(select(Certificate).where(
        Certificate.verification_code == code.strip().upper()))
    if not cert:
        return VerifyResult(valid=False)
    r, holder = _read(db, cert), db.get(User, cert.user_id)
    return VerifyResult(valid=True, holder_name=holder.full_name, event_title=r.event_title,
                        club_name=r.club_name, date_text=r.date_text,
                        attendance_percentage=r.attendance_percentage, issued_at=r.issued_at)


# ---------------- PDF ----------------
def _latin(text: str) -> str:
    # PDF base fonts are Latin-1 only. Other scripts (e.g. Arabic) print as '?' in the PDF;
    # the on-screen certificate page handles every script.
    return text.encode("latin-1", "replace").decode("latin-1")


def render_pdf(db: Session, user: User, certificate_id: uuid.UUID, base_url: str) -> tuple[bytes, str]:
    from reportlab.lib.colors import HexColor           # imported here so the app starts
    from reportlab.lib.pagesizes import A4, landscape   # even if reportlab isn't installed yet
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    d = get_certificate(db, user, certificate_id, base_url)
    ink, gold, brand, grey = HexColor("#0F2742"), HexColor("#F4B31D"), HexColor("#0B7A75"), HexColor("#3B4A5C")
    W, H = landscape(A4)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(f"Certificate: {_latin(d.event_title)}")

    c.setStrokeColor(ink); c.setLineWidth(3); c.rect(24, 24, W - 48, H - 48)
    c.setStrokeColor(gold); c.setLineWidth(1.2); c.rect(32, 32, W - 64, H - 64)

    def centered(text, y, font, size, color, max_w=W - 150):
        text = _latin(text)
        while size > 12 and stringWidth(text, font, size) > max_w:
            size -= 1
        c.setFillColor(color); c.setFont(font, size); c.drawCentredString(W / 2, y, text)

    centered("Campus Event Management Framework", H - 92, "Helvetica-Bold", 12, brand)
    centered("Certificate of Attendance", H - 148, "Times-Bold", 40, ink)
    centered("This certifies that", H - 196, "Helvetica", 14, grey)
    centered(d.holder_name, H - 250, "Times-BoldItalic", 40, ink)
    c.setStrokeColor(gold); c.setLineWidth(1.5); c.line(W / 2 - 200, H - 264, W / 2 + 200, H - 264)
    centered("attended", H - 294, "Helvetica", 14, grey)
    centered(d.event_title, H - 330, "Helvetica-Bold", 24, ink)
    centered(f"Organised by {d.club_name}", H - 358, "Helvetica", 14, grey)
    centered(d.date_text, H - 378, "Helvetica", 14, grey)
    centered(f"Attendance: {d.attendance_percentage:g}% of sessions", H - 402, "Helvetica", 12, grey)

    issued = d.issued_at.astimezone(_tz())
    c.setFillColor(grey); c.setFont("Helvetica", 10)
    c.drawString(70, 92, f"Issued on {issued.day} {issued.strftime('%B %Y')}")
    c.drawString(70, 76, f"Verification code: {d.verification_code}")
    c.drawString(70, 60, _latin(f"Verify at {d.verify_url}"))
    c.drawImage(ImageReader(io.BytesIO(_qr_png(d.verify_url))), W - 70 - 84, 56, 84, 84)
    c.setFont("Helvetica", 8); c.drawCentredString(W - 70 - 42, 46, "Scan to verify")
    c.showPage(); c.save()
    return buf.getvalue(), f"certificate-{d.verification_code}.pdf"
