import uuid

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.common.enums import EventStatus


class FeedbackCreate(BaseModel):
    overall_rating: int = Field(ge=1, le=5)
    content_rating: int | None = Field(default=None, ge=1, le=5)
    organization_rating: int | None = Field(default=None, ge=1, le=5)
    venue_rating: int | None = Field(default=None, ge=1, le=5)
    comments: str | None = Field(default=None, max_length=2000)
    suggestions: str | None = Field(default=None, max_length=2000)
    is_anonymous: bool = False   # hides your name from the organisers' report

    @field_validator("comments", "suggestions")
    @classmethod
    def _blank_to_none(cls, v):
        v = v.strip() if v else v
        return v or None


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    overall_rating: int
    content_rating: int | None
    organization_rating: int | None
    venue_rating: int | None
    comments: str | None
    suggestions: str | None
    is_anonymous: bool
    created_at: AwareDatetime


class FeedbackStatus(BaseModel):
    can_submit: bool
    reason: str | None = None            # why not, when can_submit is false
    submitted: FeedbackRead | None = None


# ---------- organiser reports ----------
class RatingAverages(BaseModel):
    overall: float | None
    content: float | None
    organization: float | None
    venue: float | None


class FeedbackComment(BaseModel):
    author: str | None            # None = the student chose to stay anonymous
    overall_rating: int
    comments: str | None
    suggestions: str | None
    created_at: AwareDatetime


class FeedbackReport(BaseModel):
    event_id: uuid.UUID
    event_title: str
    event_status: EventStatus
    registered_total: int
    attended_total: int
    attendance_rate: float | None        # attended / registered, %
    response_count: int
    response_rate: float | None          # responses / attended, %
    averages: RatingAverages
    overall_distribution: list[int]      # counts for 1, 2, 3, 4, 5 stars
    comments: list[FeedbackComment]


class EventFeedbackRow(BaseModel):
    event_id: uuid.UUID
    title: str
    start_time: AwareDatetime
    status: EventStatus
    registered: int
    attended: int
    responses: int
    average_overall: float | None


class ClubFeedbackSummary(BaseModel):
    events: list[EventFeedbackRow]
    total_responses: int
    average_overall: float | None
