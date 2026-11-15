import uuid
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.common.enums import BookingStatus, ResourceType


class ResourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    resource_type: ResourceType
    description: str | None = None
    location: str | None = Field(default=None, max_length=200)
    capacity: int | None = Field(default=None, gt=0)      # seats (venues)
    total_quantity: int = Field(default=1, ge=1)           # units (equipment)

    @model_validator(mode="after")
    def _check(self):
        if self.resource_type == ResourceType.VENUE:
            if self.capacity is None:
                raise ValueError("Venues need a capacity")
            self.total_quantity = 1  # a venue is a single bookable unit
        return self


class ResourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    location: str | None = Field(default=None, max_length=200)
    capacity: int | None = Field(default=None, gt=0)
    total_quantity: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class ResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    resource_type: ResourceType
    description: str | None
    location: str | None
    capacity: int | None
    total_quantity: int
    is_active: bool


class BookingCreate(BaseModel):
    event_id: uuid.UUID | None = None
    # If event_id is given and times are omitted, the event's own times are used.
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    quantity: int = Field(default=1, ge=1)
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("Provide both start_time and end_time, or neither")
        if self.start_time and self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.event_id is None and self.start_time is None:
            raise ValueError("start_time and end_time are required when no event_id is given")
        return self


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resource_id: uuid.UUID
    event_id: uuid.UUID | None
    requested_by: uuid.UUID
    start_time: AwareDatetime
    end_time: AwareDatetime
    quantity: int
    status: BookingStatus
    notes: str | None


class BookingStatusUpdate(BaseModel):
    status: Literal[BookingStatus.APPROVED, BookingStatus.REJECTED]


class Availability(BaseModel):
    resource_id: uuid.UUID
    start_time: AwareDatetime
    end_time: AwareDatetime
    available: bool
    remaining_quantity: int


class BookingDetail(BookingRead):
    """Booking plus readable names, for the admin review list."""
    resource_name: str = ""
    event_title: str | None = None
