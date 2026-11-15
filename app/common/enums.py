from enum import Enum


class GlobalRole(str, Enum):
    """Platform-wide role stored on the user."""
    STUDENT = "student"
    SYSTEM_ADMIN = "system_admin"


class ClubRole(str, Enum):
    """Club-scoped role stored on the membership. Higher rank = more authority."""
    MEMBER = "member"
    COMMITTEE_LEADER = "committee_leader"
    PRESIDENT = "president"

    @property
    def rank(self) -> int:
        return {"member": 1, "committee_leader": 2, "president": 3}[self.value]

    def at_least(self, other: "ClubRole") -> bool:
        return self.rank >= other.rank


class ClubStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class ApplicationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class EventCategory(str, Enum):
    ACADEMIC = "academic"
    WORKSHOP = "workshop"
    SOCIAL = "social"
    SPORTS = "sports"
    CULTURAL = "cultural"
    CAREER = "career"
    COMPETITION = "competition"
    OTHER = "other"


class EventStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class RegistrationStatus(str, Enum):
    CONFIRMED = "confirmed"
    WAITLISTED = "waitlisted"
    CANCELLED = "cancelled"


class AttendanceMethod(str, Enum):
    QR_SCAN = "qr_scan"
    MANUAL = "manual"


class ResourceType(str, Enum):
    VENUE = "venue"          # exclusive: one booking at a time (halls, labs)
    EQUIPMENT = "equipment"  # pooled: total_quantity units (projectors, speakers)


class BookingStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
