import uuid

from fastapi import APIRouter, status

from app.common.enums import RegistrationStatus
from app.core.database import DbSession
from app.core.deps import CurrentUser
from app.modules.registrations import service
from app.modules.registrations.schemas import (AttendeeRead, MyRegistration, RegistrationRead,
                                               TicketRead)

router = APIRouter(tags=["registrations"])


@router.post("/events/{event_id}/register", response_model=RegistrationRead,
             status_code=status.HTTP_201_CREATED)
def register(event_id: uuid.UUID, db: DbSession, user: CurrentUser):
    """Takes a seat if one is free (and issues the ticket), otherwise joins the waitlist."""
    return service.register(db, user, event_id)


@router.delete("/events/{event_id}/register", response_model=RegistrationRead)
def cancel_registration(event_id: uuid.UUID, db: DbSession, user: CurrentUser):
    """Cancels your registration; the oldest waitlisted student then gets the seat."""
    return service.cancel_registration(db, user, event_id)


@router.get("/events/{event_id}/my-registration", response_model=RegistrationRead | None)
def my_registration(event_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return service.get_my_registration(db, user, event_id)


@router.get("/events/{event_id}/registrations", response_model=list[AttendeeRead])
def event_attendees(event_id: uuid.UUID, db: DbSession, user: CurrentUser,
                    status: RegistrationStatus | None = None):
    """Attendee list for the event's club leaders (and admins)."""
    return service.list_attendees(db, user, event_id, status)


@router.get("/registrations/me", response_model=list[MyRegistration])
def my_registrations(db: DbSession, user: CurrentUser):
    return service.list_my_registrations(db, user)


@router.get("/registrations/{registration_id}/ticket", response_model=TicketRead)
def get_ticket(registration_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return service.get_ticket(db, user, registration_id)
