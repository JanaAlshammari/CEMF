import uuid

from fastapi import APIRouter, Depends, Query, status

from app.common.enums import BookingStatus, ResourceType
from app.core.database import DbSession
from app.core.deps import CurrentUser, require_admin
from app.modules.resources import service
from app.modules.resources.schemas import (Availability, BookingCreate, BookingDetail, BookingRead,
                                            BookingStatusUpdate, ResourceCreate, ResourceRead,
                                            ResourceUpdate)
from pydantic import AwareDatetime

router = APIRouter(tags=["resources"])


# ----- catalogue -----
@router.get("/resources", response_model=list[ResourceRead])
def list_resources(db: DbSession, resource_type: ResourceType | None = None):
    return service.list_resources(db, resource_type)


@router.get("/resources/{resource_id}", response_model=ResourceRead)
def get_resource(resource_id: uuid.UUID, db: DbSession):
    return service.get_resource_or_404(db, resource_id)


@router.post("/resources", response_model=ResourceRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
def create_resource(data: ResourceCreate, db: DbSession):
    return service.create_resource(db, data)


@router.patch("/resources/{resource_id}", response_model=ResourceRead,
              dependencies=[Depends(require_admin)])
def update_resource(resource_id: uuid.UUID, data: ResourceUpdate, db: DbSession):
    return service.update_resource(db, resource_id, data)


# ----- availability & calendar -----
@router.get("/resources/{resource_id}/availability", response_model=Availability)
def check_availability(
    resource_id: uuid.UUID, db: DbSession, _: CurrentUser,
    start: AwareDatetime = Query(...), end: AwareDatetime = Query(...),
):
    resource = service.get_resource_or_404(db, resource_id)
    remaining = service.remaining_quantity(db, resource, start, end)
    return Availability(resource_id=resource.id, start_time=start, end_time=end,
                        available=resource.is_active and remaining > 0, remaining_quantity=remaining)


@router.get("/resources/{resource_id}/bookings", response_model=list[BookingRead])
def resource_calendar(
    resource_id: uuid.UUID, db: DbSession, _: CurrentUser,
    start: AwareDatetime | None = None, end: AwareDatetime | None = None,
):
    """Upcoming active bookings for a resource (defaults to 'from now')."""
    service.get_resource_or_404(db, resource_id)
    return service.list_bookings(db, resource_id, start, end)


# ----- bookings -----
@router.post("/resources/{resource_id}/bookings", response_model=BookingRead,
             status_code=status.HTTP_201_CREATED)
def request_booking(resource_id: uuid.UUID, data: BookingCreate, db: DbSession, user: CurrentUser):
    return service.request_booking(db, user, resource_id, data)


@router.get("/bookings", response_model=list[BookingDetail], dependencies=[Depends(require_admin)])
def list_bookings_for_review(
    db: DbSession, booking_status: BookingStatus = Query(BookingStatus.PENDING, alias="status")
):
    """Admin review queue (defaults to pending requests)."""
    return service.list_bookings_by_status(db, booking_status)


@router.patch("/bookings/{booking_id}/status", response_model=BookingRead,
              dependencies=[Depends(require_admin)])
def review_booking(booking_id: uuid.UUID, body: BookingStatusUpdate, db: DbSession):
    """Admin approves or rejects a pending booking."""
    return service.set_booking_status(db, booking_id, body.status)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingRead)
def cancel_booking(booking_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return service.cancel_booking(db, user, booking_id)
