from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.services.logging_service import dashboard_stats, get_login_logs, get_unknown_faces

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """
    Simple server-rendered admin dashboard. Auth is intentionally left
    out of this page for demo simplicity — in production, protect it
    the same way as the /api endpoints (JWT cookie + require_role).
    """
    stats = dashboard_stats(db)
    recent_logs = get_login_logs(db, limit=10)
    recent_unknown = get_unknown_faces(db, limit=10)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "stats": stats,
            "recent_logs": recent_logs,
            "recent_unknown": recent_unknown,
            "camera_api_key": settings.CAMERA_API_KEY,
        },
    )
