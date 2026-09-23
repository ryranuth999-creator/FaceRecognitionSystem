from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.notifications.email import send_unknown_person_email
from app.notifications.telegram import send_unknown_person_alert
from app.schemas.auth import LoginLogOut, UnknownFaceOut
from app.services.logging_service import dashboard_stats, get_login_logs, get_unknown_faces

router = APIRouter(prefix="/api", tags=["logs"])


@router.get("/logs", response_model=List[LoginLogOut])
def list_logs(
    result: Optional[str] = Query(default=None, pattern="^(success|failed)$"),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator", "viewer")),
):
    return get_login_logs(db, result=result, limit=limit)


@router.get("/unknown", response_model=List[UnknownFaceOut])
def list_unknown(
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator", "viewer")),
):
    return get_unknown_faces(db, limit=limit)


@router.get("/dashboard/stats")
def stats(db: Session = Depends(get_db), _admin=Depends(require_role("admin", "operator", "viewer"))):
    return dashboard_stats(db)


@router.post("/send-alert")
async def resend_alert(
    unknown_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator")),
):
    """Manually re-trigger Telegram/email alerts for a previously
    logged unknown-face event (e.g. if the first attempt failed)."""
    from app.models.log import UnknownFace  # local import to avoid cycle

    record = db.query(UnknownFace).filter(UnknownFace.UnknownID == unknown_id).first()
    if not record:
        return {"detail": "Unknown face record not found"}

    from app.models.user import Camera
    camera = db.query(Camera).filter(Camera.CameraID == record.CameraID).first()
    camera_name = camera.CameraName if camera else (record.CameraID or "N/A")

    timestamp_str = record.Time.strftime("%Y-%m-%d %H:%M")
    telegram_ok = await send_unknown_person_alert(
        photo_path=record.Photo, camera_name=camera_name, confidence=record.Confidence or 0.0,
        timestamp=timestamp_str,
    )
    email_ok = await send_unknown_person_email(
        photo_path=record.Photo,
        camera_name=camera_name,
        confidence=record.Confidence or 0.0,
        timestamp=timestamp_str,
        ip_address="N/A",
    )
    record.AlertSent = record.AlertSent or telegram_ok
    record.EmailSent = record.EmailSent or email_ok
    db.commit()
    return {"telegram_sent": telegram_ok, "email_sent": email_ok}
