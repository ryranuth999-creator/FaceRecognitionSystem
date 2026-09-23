from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.user import Camera
from app.schemas.auth import CameraOut

router = APIRouter(prefix="/api", tags=["cameras"])


@router.get("/cameras", response_model=List[CameraOut])
def list_cameras(db: Session = Depends(get_db), _admin=Depends(require_role("admin", "operator", "viewer"))):
    return db.query(Camera).all()


@router.post("/camera/start")
def start_camera(camera_id: str, db: Session = Depends(get_db), _admin=Depends(require_role("admin", "operator"))):
    """
    Marks a camera as online. Actual video capture for a given camera
    is expected to run as a separate long-lived process/service (see
    training/live_recognition.py) that posts frames to /api/auth/login-face;
    this endpoint just updates status for the dashboard.
    """
    camera = db.query(Camera).filter(Camera.CameraID == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    camera.Status = "online"
    db.commit()
    return {"detail": f"Camera {camera_id} marked online"}


@router.post("/camera/stop")
def stop_camera(camera_id: str, db: Session = Depends(get_db), _admin=Depends(require_role("admin", "operator"))):
    camera = db.query(Camera).filter(Camera.CameraID == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    camera.Status = "offline"
    db.commit()
    return {"detail": f"Camera {camera_id} marked offline"}
