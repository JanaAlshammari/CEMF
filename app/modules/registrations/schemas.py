import uuid

from pydantic import AwareDatetime, BaseModel

from app.common.enums import EventStatus, RegistrationStatus


class RegistrationRead(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    user_id: uuid.UUID
    status: RegistrationStatus
    registered_at: AwareDatetime
    cancelled_at: AwareDatetime | None = None
    queue_position: int | None = None  # 1 = next in line (waitlisted only)


class MyRegistration(RegistrationRead):
    event_title: str
    event_start_time: AwareDatetime
    event_end_time: AwareDatetime
    event_status: EventStatus


class AttendeeRead(BaseModel):
    registration_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str
    student_id: str | None
    status: RegistrationStatus
    registered_at: AwareDatetime


class TicketRead(BaseModel):
    id: uuid.UUID
    registration_id: uuid.UUID
    event_id: uuid.UUID
    event_title: str
    event_start_time: AwareDatetime
    event_end_time: AwareDatetime
    venue_name: str | None
    holder_name: str
    student_id: str | None
    ticket_code: str
    is_valid: bool
    issued_at: AwareDatetime
    qr_payload: str   # what the QR encodes; the attendance scanner reads this
    qr_image: str     # PNG as a data: URL, ready for <img src>
