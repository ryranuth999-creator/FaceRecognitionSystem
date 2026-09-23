import numpy as np
import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, Header, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.schemas.auth import FaceLoginResponse, Token
from app.services.attendance import authenticate_frame
from app.core.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/token", response_model=Token)
def admin_login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Standard username/password login for the admin dashboard (JWT)."""
    user = db.query(User).filter(User.EmployeeID == form_data.username).first()
    if not user or not user.HashedPassword or not verify_password(form_data.password, user.HashedPassword):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=user.EmployeeID, role=user.Role)
    return Token(access_token=token)


@router.post("/login-face", response_model=FaceLoginResponse)
async def login_face(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="A single JPEG/PNG frame captured from the camera"),
    camera_id: str = Form(default="CAM-01"),
    x_camera_key: str = Header(default="", description="Camera authentication key"),
    db: Session = Depends(get_db),
):
    """
    Physical/attendance login: upload one camera frame, the server
    detects + recognizes the face, logs the attempt, and (if unknown)
    fires Telegram + email alerts.
    """
    if settings.CAMERA_API_KEY and x_camera_key != settings.CAMERA_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Camera API Key")

    contents = await file.read()
    npimg = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode uploaded image")

    client_ip = "N/A"
    result = await authenticate_frame(db, frame, camera_id=camera_id, ip_address=client_ip, background_tasks=background_tasks)
    return result
