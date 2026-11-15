import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.enums import BookingStatus, ClubRole, EventStatus, GlobalRole, ResourceType
from app.core.deps import check_club_access
from app.modules.events.models import Event
from app.modules.identity.models import User
from app.modules.resources.models import Resource, ResourceBooking
from app.modules.resources.schemas import (BookingCreate, BookingDetail, ResourceCreate,
                                            ResourceUpdate)

# Bookings in these states "hold" the slot. Rejected/cancelled ones free it.
ACTIVE_STATUSES = (BookingStatus.PENDING, BookingStatus.APPROVED)


# ---------------- resources ----------------
def create_resource(db: Session, data: ResourceCreate) -> Resource:
    if db.scalar(select(Resource).where(Resource.name == data.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A resource with this name already exists")
    resource = Resource(**data.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def get_resource_or_404(db: Session, resource_id: uuid.UUID) -> Resource:
    resource = db.get(Resource, resource_id)
    if not resource:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")
    return resource


def update_resource(db: Session, resource_id: uuid.UUID, data: ResourceUpdate) -> Resource:
    resource = get_resource_or_404(db, resource_id)
    changes = data.model_dump(exclude_unset=True)
    if resource.resource_type == ResourceType.VENUE:
        changes.pop("total_quantity", None)
    for key, value in changes.items():
        if value is None and key in {"name", "is_active", "total_quantity"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{key} cannot be null")
        setattr(resource, key, value)
    db.commit()
    db.refresh(resource)
    return resource


def list_resources(db: Session, resource_type: ResourceType | None, include_inactive: bool = False):
    stmt = select(Resource).order_by(Resource.name)
    if resource_type:
        stmt = stmt.where(Resource.resource_type == resource_type)
    if not include_inactive:
        stmt = stmt.where(Resource.is_active.is_(True))
    return db.scalars(stmt).all()


# ---------------- availability ----------------
def _overlap_conditions(resource_id: uuid.UUID, start: datetime, end: datetime):
    # Half-open intervals: a booking ending at 10:00 doesn't clash with one starting at 10:00.
    return (
        ResourceBooking.resource_id == resource_id,
        ResourceBooking.status.in_(ACTIVE_STATUSES),
        ResourceBooking.start_time < end,
        ResourceBooking.end_time > start,
    )


def remaining_quantity(db: Session, resource: Resource, start: datetime, end: datetime) -> int:
    """Units still free during [start, end). Venues have total_quantity = 1, so the same
    maths covers both kinds. Note: this sums every booking overlapping the window, which is
    slightly conservative for equipment (may refuse a request that would technically fit)."""
    used = db.scalar(
        select(func.coalesce(func.sum(ResourceBooking.quantity), 0)).where(
            *_overlap_conditions(resource.id, start, end)
        )
    )
    return max(resource.total_quantity - used, 0)


# ---------------- bookings ----------------
def create_booking(
    db: Session,
    *,
    resource_id: uuid.UUID,
    requested_by: uuid.UUID,
    start: datetime,
    end: datetime,
    quantity: int = 1,
    event_id: uuid.UUID | None = None,
    notes: str | None = None,
    commit: bool = True,
) -> ResourceBooking:
    """Core conflict-checked booking. Pass commit=False to compose it inside a larger
    transaction (the events service does this when creating an event + its venue booking)."""
    if end <= start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "end_time must be after start_time")

    # Row lock: concurrent requests for the same resource queue up here, so two people
    # can't both pass the availability check for the last projector.
    resource = db.scalar(select(Resource).where(Resource.id == resource_id).with_for_update())
    if not resource or not resource.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found or inactive")

    is_exclusive = resource.resource_type == ResourceType.VENUE
    if is_exclusive:
        quantity = 1
    remaining = remaining_quantity(db, resource, start, end)
    if quantity > remaining:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"'{resource.name}' is not available for that period (remaining: {remaining})",
        )

    booking = ResourceBooking(
        resource_id=resource.id,
        event_id=event_id,
        requested_by=requested_by,
        start_time=start,
        end_time=end,
        quantity=quantity,
        is_exclusive=is_exclusive,
        status=BookingStatus.PENDING,
        notes=notes,
    )
    db.add(booking)
    try:
        db.flush()  # the DB exclusion constraint is the final safety net for venues
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "That time slot was just taken")
    if commit:
        db.commit()
        db.refresh(booking)
    return booking


def request_booking(
    db: Session, user: User, resource_id: uuid.UUID, data: BookingCreate
) -> ResourceBooking:
    """Who may book: committee leaders+ of the event's club (booking is tied to an event),
    or a system admin for ad-hoc bookings."""
    start, end = data.start_time, data.end_time
    if data.event_id:
        event = db.get(Event, data.event_id)
        if not event:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
        check_club_access(db, user, event.club_id, ClubRole.COMMITTEE_LEADER)
        if event.status in (EventStatus.CANCELLED, EventStatus.COMPLETED):
            raise HTTPException(status.HTTP_409_CONFLICT, "Event is no longer active")
        start, end = start or event.start_time, end or event.end_time
    elif user.global_role != GlobalRole.SYSTEM_ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Bookings must be linked to an event (admins excepted)"
        )
    return create_booking(
        db,
        resource_id=resource_id,
        requested_by=user.id,
        start=start,
        end=end,
        quantity=data.quantity,
        event_id=data.event_id,
        notes=data.notes,
    )


def get_booking_or_404(db: Session, booking_id: uuid.UUID) -> ResourceBooking:
    booking = db.get(ResourceBooking, booking_id)
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    return booking


def set_booking_status(db: Session, booking_id: uuid.UUID, new_status: BookingStatus) -> ResourceBooking:
    booking = get_booking_or_404(db, booking_id)
    if booking.status != BookingStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Booking is already {booking.status.value}")
    booking.status = new_status
    db.commit()
    db.refresh(booking)
    return booking


def cancel_booking(db: Session, user: User, booking_id: uuid.UUID) -> ResourceBooking:
    booking = get_booking_or_404(db, booking_id)
    if booking.requested_by != user.id and user.global_role != GlobalRole.SYSTEM_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your booking")
    if booking.status not in ACTIVE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Booking is already {booking.status.value}")
    booking.status = BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)
    return booking


def cancel_bookings_for_event(db: Session, event_id: uuid.UUID) -> None:
    """No commit: the caller owns the transaction."""
    db.execute(
        update(ResourceBooking)
        .where(ResourceBooking.event_id == event_id, ResourceBooking.status.in_(ACTIVE_STATUSES))
        .values(status=BookingStatus.CANCELLED)
    )


def list_bookings(
    db: Session, resource_id: uuid.UUID, start: datetime | None, end: datetime | None
) -> list[ResourceBooking]:
    start = start or datetime.now(timezone.utc)
    stmt = select(ResourceBooking).where(
        ResourceBooking.resource_id == resource_id,
        ResourceBooking.status.in_(ACTIVE_STATUSES),
        ResourceBooking.end_time > start,
    )
    if end:
        stmt = stmt.where(ResourceBooking.start_time < end)
    return list(db.scalars(stmt.order_by(ResourceBooking.start_time)).all())


def list_bookings_by_status(db: Session, booking_status: BookingStatus) -> list[BookingDetail]:
    rows = db.execute(
        select(ResourceBooking, Resource.name, Event.title)
        .join(Resource, Resource.id == ResourceBooking.resource_id)
        .outerjoin(Event, Event.id == ResourceBooking.event_id)
        .where(ResourceBooking.status == booking_status)
        .order_by(ResourceBooking.start_time)
    ).all()
    return [
        BookingDetail.model_validate(b).model_copy(
            update={"resource_name": resource_name, "event_title": event_title}
        )
        for b, resource_name, event_title in rows
    ]
