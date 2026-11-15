import uuid
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.common.enums import EventStatus


class ScanRequest(BaseModel):
    payload: str = Field(min_length=1, max_length=500)   # the text inside the ticket's QR code
    session_id: uuid.UUID | None = None                   # omit = whichever session is open now


class ManualCheckIn(BaseModel):
    registration_id: uuid.UUID
    session_id: uuid.UUID | None = None


class ScanResult(BaseModel):
    result: Literal["checked_in", "already_checked_in"]
    attendee_name: str
    student_id: str | None
    session_id: uuid.UUID
    session_title: str
    scanned_at: AwareDatetime


class SessionStat(BaseModel):
    id: uuid.UUID
    title: str
    start_time: AwareDatetime
    end_time: AwareDatetime
    checked_in: int


class AttendeeAttendance(BaseModel):
    registration_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str
    student_id: str | None
    attended_session_ids: list[uuid.UUID]
    sessions_attended: int
    total_sessions: int
    percentage: float
    eligible: bool
    certificate_issued: bool


class AttendanceReport(BaseModel):
    event_id: uuid.UUID
    event_title: str
    event_status: EventStatus
    certificate_enabled: bool
    required_percentage: float
    registered_total: int
    checked_in_total: int       # people with at least one check-in
    sessions: list[SessionStat]
    attendees: list[AttendeeAttendance]


class MyAttendance(BaseModel):
    event_id: uuid.UUID
    sessions_attended: int
    total_sessions: int
    percentage: float
    required_percentage: float
    certificate_enabled: bool
    event_over: bool
    eligible: bool
    certificate_id: uuid.UUID | None


class CertificateRead(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    event_title: str
    club_name: str
    event_start_time: AwareDatetime
    event_end_time: AwareDatetime
    date_text: str
    verification_code: str
    attendance_percentage: float
    issued_at: AwareDatetime


class CertificateDetail(CertificateRead):
    holder_name: str
    student_id: str | None
    verify_url: str
    qr_image: str   # PNG data: URL of the verification link


class VerifyResult(BaseModel):
    valid: bool
    holder_name: str | None = None
    event_title: str | None = None
    club_name: str | None = None
    date_text: str | None = None
    attendance_percentage: float | None = None
    issued_at: AwareDatetime | None = None
