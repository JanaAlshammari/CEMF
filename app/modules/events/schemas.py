import uuid
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.common.enums import EventCategory, EventStatus


class SessionCreate(BaseModel):
    title: str = Field(default="Session", max_length=200)
    start_time: AwareDatetime
    end_time: AwareDatetime

    @model_validator(mode="after")
    def _check(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    start_time: AwareDatetime
    end_time: AwareDatetime


class EventCreate(BaseModel):
    club_id: uuid.UUID
    title: str = Field(min_length=3, max_length=200)
    description: str | None = None
    category: EventCategory = EventCategory.OTHER
    banner_url: str | None = Field(default=None, max_length=500)
    start_time: AwareDatetime
    end_time: AwareDatetime
    registration_deadline: AwareDatetime | None = None
    capacity: int = Field(gt=0)
    venue_id: uuid.UUID | None = None
    certificate_enabled: bool = True
    certificate_min_attendance: Decimal = Field(default=Decimal("75"), ge=0, le=100)
    # Optional. Omit for a single-session event (one is created automatically).
    sessions: list[SessionCreate] = []

    @model_validator(mode="after")
    def _check(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.registration_deadline and self.registration_deadline > self.start_time:
            raise ValueError("registration_deadline must be before the event starts")
        return self


class EventUpdate(BaseModel):
    """Only send the fields you want to change. Schedule/venue fields (start_time, end_time,
    venue_id) can only be changed while the event is still a draft."""
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    category: EventCategory | None = None
    banner_url: str | None = Field(default=None, max_length=500)
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    registration_deadline: AwareDatetime | None = None
    capacity: int | None = Field(default=None, gt=0)
    venue_id: uuid.UUID | None = None
    certificate_enabled: bool | None = None
    certificate_min_attendance: Decimal | None = Field(default=None, ge=0, le=100)


class EventSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    club_id: uuid.UUID
    title: str
    description: str | None
    category: EventCategory
    banner_url: str | None
    start_time: AwareDatetime
    end_time: AwareDatetime
    registration_deadline: AwareDatetime | None
    capacity: int
    venue_id: uuid.UUID | None
    status: EventStatus
    registered_count: int = 0   # filled in by the service
    seats_left: int = 0         # filled in by the service


class EventRead(EventSummary):
    certificate_enabled: bool
    certificate_min_attendance: Decimal
    sessions: list[SessionRead]
