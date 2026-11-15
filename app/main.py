from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.modules.attendance.router import router as attendance_router
from app.modules.clubs.router import router as clubs_router
from app.modules.events.router import router as events_router
from app.modules.feedback.router import router as feedback_router
from app.modules.identity.router import router as identity_router
from app.modules.registrations.router import router as registrations_router
from app.modules.resources.router import router as resources_router
from app.web.router import WEB_DIR, router as web_router

app = FastAPI(title=settings.app_name, version="0.6.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JSON API: one router per service (all six services are now mounted)
for r in (identity_router, clubs_router, resources_router, events_router, registrations_router,
          attendance_router, feedback_router):
    app.include_router(r, prefix=settings.api_prefix)

# Website
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
app.include_router(web_router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
