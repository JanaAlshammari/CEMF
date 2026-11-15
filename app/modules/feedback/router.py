import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.common.enums import ClubRole
from app.core.database import DbSession
from app.core.deps import ClubAccess, CurrentUser, require_club_role
from app.modules.feedback import service
from app.modules.feedback.schemas import (ClubFeedbackSummary, FeedbackCreate, FeedbackRead,
                                          FeedbackReport, FeedbackStatus)

router = APIRouter(tags=["feedback"])


# ----- attendees -----
@router.get("/events/{event_id}/feedback/status", response_model=FeedbackStatus)
def feedback_status(event_id: uuid.UUID, db: DbSession, user: CurrentUser):
    """Can I rate this event? If I already did, returns my answers."""
    return service.feedback_status(db, user, event_id)


@router.post("/events/{event_id}/feedback", response_model=FeedbackRead,
             status_code=status.HTTP_201_CREATED)
def submit_feedback(event_id: uuid.UUID, body: FeedbackCreate, db: DbSession, user: CurrentUser):
    return service.save_feedback(db, user, event_id, body, update=False)


@router.put("/events/{event_id}/feedback", response_model=FeedbackRead)
def update_feedback(event_id: uuid.UUID, body: FeedbackCreate, db: DbSession, user: CurrentUser):
    return service.save_feedback(db, user, event_id, body, update=True)


# ----- organisers (committee leaders and above) -----
@router.get("/events/{event_id}/feedback/report", response_model=FeedbackReport)
def feedback_report(event_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return service.feedback_report(db, user, event_id)


@router.get("/events/{event_id}/feedback/report.csv")
def feedback_report_csv(event_id: uuid.UUID, db: DbSession, user: CurrentUser):
    text, filename = service.feedback_csv(db, user, event_id)
    return Response(text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/clubs/{club_id}/feedback-summary", response_model=ClubFeedbackSummary)
def club_feedback_summary(
    club_id: uuid.UUID, db: DbSession,
    _: Annotated[ClubAccess, Depends(require_club_role(ClubRole.COMMITTEE_LEADER))],
):
    return service.club_summary(db, club_id)
