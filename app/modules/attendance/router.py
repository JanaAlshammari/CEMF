import uuid

from fastapi import APIRouter, Request, Response, status

from app.core.database import DbSession
from app.core.deps import CurrentUser
from app.modules.attendance import certificates, service
from app.modules.attendance.schemas import (AttendanceReport, CertificateDetail, CertificateRead,
                                            ManualCheckIn, MyAttendance, ScanRequest, ScanResult,
                                            VerifyResult)

router = APIRouter(tags=["attendance & certificates"])


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


# ----- check-in (committee leaders and above) -----
@router.post("/events/{event_id}/attendance/scan", response_model=ScanResult)
def scan_ticket(event_id: uuid.UUID, body: ScanRequest, db: DbSession, user: CurrentUser):
    """Verify a scanned QR code and log attendance. Scanning twice is harmless."""
    return service.check_in_by_qr(db, user, event_id, body.payload, body.session_id)


@router.post("/events/{event_id}/attendance/manual", response_model=ScanResult)
def manual_check_in(event_id: uuid.UUID, body: ManualCheckIn, db: DbSession, user: CurrentUser):
    return service.check_in_manual(db, user, event_id, body.registration_id, body.session_id)


@router.get("/events/{event_id}/attendance", response_model=AttendanceReport)
def attendance_report(event_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return service.attendance_report(db, user, event_id)


# ----- student: own attendance and certificate -----
@router.get("/events/{event_id}/my-attendance", response_model=MyAttendance)
def my_attendance(event_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return certificates.my_attendance(db, user, event_id)


@router.post("/events/{event_id}/certificate", response_model=CertificateRead,
             status_code=status.HTTP_201_CREATED)
def claim_certificate(event_id: uuid.UUID, request: Request, db: DbSession, user: CurrentUser):
    """Issues your certificate if the event has ended and you met the attendance threshold."""
    return certificates.claim_certificate(db, user, event_id, _base(request))


# ----- certificates -----
@router.get("/certificates/me", response_model=list[CertificateRead])
def my_certificates(db: DbSession, user: CurrentUser):
    return certificates.list_my_certificates(db, user)


@router.get("/certificates/verify/{code}", response_model=VerifyResult)
def verify_certificate(code: str, db: DbSession):
    """Public: anyone holding a certificate's code can confirm it is genuine."""
    return certificates.verify(db, code)


@router.get("/certificates/{certificate_id}", response_model=CertificateDetail)
def get_certificate(certificate_id: uuid.UUID, request: Request, db: DbSession, user: CurrentUser):
    return certificates.get_certificate(db, user, certificate_id, _base(request))


@router.get("/certificates/{certificate_id}/pdf")
def download_certificate_pdf(certificate_id: uuid.UUID, request: Request, db: DbSession,
                             user: CurrentUser):
    pdf, filename = certificates.render_pdf(db, user, certificate_id, _base(request))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
