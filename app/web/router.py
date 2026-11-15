"""Server-rendered pages. Pages are thin shells: the browser fetches data from /api/v1."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

WEB_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
router = APIRouter(include_in_schema=False)


def _page(template_name: str):
    def handler(request: Request):
        return templates.TemplateResponse(request, template_name)

    return handler


PAGES = {
    "/": "home.html",
    "/events": "events.html",
    "/events/{event_id}": "event_detail.html",
    "/clubs": "clubs.html",
    "/tickets": "tickets.html",
    "/scan/{event_id}": "scan.html",
    "/reports/{event_id}": "report.html",
    "/certificates": "certificates.html",
    "/certificates/{certificate_id}": "certificate.html",
    "/verify": "verify.html",
    "/verify/{code}": "verify.html",
    "/tickets/{registration_id}": "ticket.html",
    "/login": "login.html",
    "/register": "register.html",
    "/manage": "manage.html",
}
for path, template_name in PAGES.items():
    router.add_api_route(path, _page(template_name), methods=["GET"], response_class=HTMLResponse)
