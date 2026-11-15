"""Demo data for LOCAL DEVELOPMENT ONLY (the passwords are public). Safe to run twice.

    python -m scripts.seed_demo

Creates 4 accounts, a club, venues/equipment, and two published events, so you can click
through the whole app straight away.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import app.models  # noqa: F401  (loads every model so relationships resolve)
from sqlalchemy import select

from app.common.enums import (BookingStatus, ClubRole, EventCategory, EventStatus, GlobalRole,
                              ResourceType)
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.clubs.models import Club, Membership
from app.modules.events.models import Event, EventSession
from app.modules.identity.models import User
from app.modules.resources.models import Resource, ResourceBooking

PASSWORD = "Demo12345"
ACCOUNTS = [
    ("admin@cemf.test", "Demo Admin", GlobalRole.SYSTEM_ADMIN, None),
    ("leader@cemf.test", "Layla Club President", GlobalRole.STUDENT, "S1001"),
    ("student1@cemf.test", "Sara Student", GlobalRole.STUDENT, "S1002"),
    ("student2@cemf.test", "Omar Student", GlobalRole.STUDENT, "S1003"),
]


def main() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == "admin@cemf.test")):
            print("Demo data already exists. Nothing to do.")
            return

        users = {}
        for email, name, role, sid in ACCOUNTS:
            u = User(email=email, full_name=name, global_role=role, student_id=sid,
                     hashed_password=hash_password(PASSWORD))
            db.add(u)
            users[email] = u
        db.flush()
        leader = users["leader@cemf.test"]

        club = Club(name="Chess Club", slug="chess-club", category="Games",
                    description="Weekly casual games, tournaments and beginner lessons for everyone.")
        club.memberships.append(Membership(user_id=leader.id, role=ClubRole.PRESIDENT))
        db.add(club)

        hall = Resource(name="Main Hall", resource_type=ResourceType.VENUE, capacity=120,
                        location="Building A, ground floor", description="Large hall with a stage.")
        lab = Resource(name="Seminar Room 2", resource_type=ResourceType.VENUE, capacity=30,
                       location="Building B, first floor")
        projector = Resource(name="Portable projector", resource_type=ResourceType.EQUIPMENT, total_quantity=3)
        sound = Resource(name="Sound system", resource_type=ResourceType.EQUIPMENT, total_quantity=1)
        db.add_all([hall, lab, projector, sound])
        db.flush()

        base = (datetime.now(timezone.utc) + timedelta(days=7)).replace(hour=15, minute=0, second=0, microsecond=0)

        # Event 1: has an approved venue booking, plenty of seats
        e1_start, e1_end = base, base + timedelta(hours=2)
        e1 = Event(club_id=club.id, created_by=leader.id, venue_id=hall.id,
                   title="Beginner Chess Night", category=EventCategory.SOCIAL, capacity=40,
                   description="Learn the rules, play a few friendly games, and meet the club.",
                   start_time=e1_start, end_time=e1_end, status=EventStatus.PUBLISHED,
                   certificate_enabled=True, certificate_min_attendance=Decimal("75"))
        e1.sessions = [EventSession(title="Main Session", start_time=e1_start, end_time=e1_end)]
        db.add(e1)
        db.flush()
        db.add(ResourceBooking(resource_id=hall.id, event_id=e1.id, requested_by=leader.id,
                               start_time=e1_start, end_time=e1_end, quantity=1, is_exclusive=True,
                               status=BookingStatus.APPROVED, notes="Demo data"))

        # Event 2: only 2 seats and two sessions, to try the waitlist and the attendance threshold
        e2_start, e2_end = base + timedelta(days=3), base + timedelta(days=3, hours=4)
        e2 = Event(club_id=club.id, created_by=leader.id, title="Chess Strategy Workshop",
                   category=EventCategory.WORKSHOP, capacity=2,
                   description="A two-part workshop on openings and endgames.",
                   start_time=e2_start, end_time=e2_end, status=EventStatus.PUBLISHED,
                   certificate_enabled=True, certificate_min_attendance=Decimal("50"))
        e2.sessions = [
            EventSession(title="Part 1: Openings", start_time=e2_start, end_time=e2_start + timedelta(hours=2)),
            EventSession(title="Part 2: Endgames", start_time=e2_start + timedelta(hours=2), end_time=e2_end),
        ]
        db.add(e2)
        db.commit()

    print("Demo data created. All accounts use the password:", PASSWORD)
    for email, name, role, _ in ACCOUNTS:
        print(f"  {email:22} {name} ({'admin' if role == GlobalRole.SYSTEM_ADMIN else 'student'})")
    print("leader@cemf.test is president of the Chess Club and can manage its events.")


if __name__ == "__main__":
    main()
