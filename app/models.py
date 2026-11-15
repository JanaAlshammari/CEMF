"""Import every model module so Base.metadata is fully populated (used by Alembic env.py)."""
from app.common.base import Base  # noqa: F401
from app.modules.identity.models import User  # noqa: F401
from app.modules.clubs.models import Club, ClubActivity, Membership, MembershipApplication  # noqa: F401
from app.modules.resources.models import Resource, ResourceBooking  # noqa: F401
from app.modules.events.models import Event, EventSession  # noqa: F401
from app.modules.registrations.models import Registration, Ticket  # noqa: F401
from app.modules.attendance.models import AttendanceRecord, Certificate  # noqa: F401
from app.modules.feedback.models import Feedback  # noqa: F401
