import logging
import time
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.staticfiles import StaticFiles

from app.api import attendance, auth, cameras, dashboard, logs, users, settings as api_settings
from app.core.config import settings
from app.core.database import init_db

logging.basicConfig(level=logging.INFO if not settings.DEBUG else logging.DEBUG)


class InMemoryRateLimiter:
    def __init__(self, limit: int = 150, window: int = 60):
        self.limit = limit
        self.window = window
        self.history = {}

    async def __call__(self, request: Request):
        # Allow static files and docs without rate limiting
        if request.url.path.startswith("/static") or request.url.path in ("/docs", "/openapi.json", "/favicon.ico"):
            return
        ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        timestamps = self.history.get(ip, [])
        timestamps = [t for t in timestamps if now - t < self.window]
        self.history[ip] = timestamps
        if len(timestamps) >= self.limit:
            raise HTTPException(status_code=429, detail="Too many requests. Rate limit exceeded.")
        self.history[ip].append(now)


rate_limiter = InMemoryRateLimiter(limit=150, window=60)

app = FastAPI(
    title="Face Recognition Authentication System",
    description=(
        "Face-recognition based authentication + attendance logging, "
        "with SQL Server persistence and Telegram/Email alerts for "
        "unknown persons."
    ),
    version="1.0.0",
    dependencies=[Depends(rate_limiter)],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(attendance.router)
app.include_router(logs.router)
app.include_router(cameras.router)
app.include_router(dashboard.router)
app.include_router(api_settings.router)


@app.on_event("startup")
def on_startup():
    init_db()
    logging.getLogger(__name__).info("Database tables verified/created. Backend=%s", settings.DB_BACKEND)


@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "app": settings.APP_NAME, "docs": "/docs", "dashboard": "/dashboard"}


@app.get("/health", tags=["health"])
def health():
    return {"status": "healthy"}


# ---------- Root Level API Routes (REST Design Alignment) ----------
from datetime import date
from typing import List, Optional
from fastapi import File, Form, UploadFile, Query, Depends, BackgroundTasks, Header
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import require_role
from app.schemas.auth import FaceLoginResponse, AttendanceOut, LoginLogOut, UnknownFaceOut
from app.schemas.user import UserOut, UserRegisterResponse

# 1. POST /register
from app.api.users import register_user as api_register_user
@app.post("/register", response_model=UserRegisterResponse, tags=["root-api"])
async def root_register(
    employee_no: str = Form(..., alias="employee_id"), # support both employee_no and employee_id form fields
    full_name: str = Form(...),
    department: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    telegram_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator")),
):
    return await api_register_user(employee_no, full_name, department, email, telegram_id, files, db, _admin)

# 2. POST /login-face
from app.api.auth import login_face as api_login_face
@app.post("/login-face", response_model=FaceLoginResponse, tags=["root-api"])
async def root_login_face(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="A single JPEG/PNG frame captured from the camera"),
    camera_id: str = Form(default="CAM-01"),
    x_camera_key: str = Header(default="", description="Camera authentication key"),
    db: Session = Depends(get_db),
):
    return await api_login_face(background_tasks, file, camera_id, x_camera_key, db)

# 3. GET /users
from app.api.users import list_users as api_list_users
@app.get("/users", response_model=List[UserOut], tags=["root-api"])
def root_list_users(
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator", "viewer")),
):
    return api_list_users(db, _admin)

# 4. GET /logs
from app.api.logs import list_logs as api_list_logs
@app.get("/logs", response_model=List[LoginLogOut], tags=["root-api"])
def root_list_logs(
    result: Optional[str] = Query(default=None, pattern="^(success|failed)$"),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator", "viewer")),
):
    return api_list_logs(result, limit, db, _admin)

# 5. GET /attendance
from app.api.attendance import list_attendance as api_list_attendance
@app.get("/attendance", response_model=List[AttendanceOut], tags=["root-api"])
def root_list_attendance(
    day: Optional[date] = Query(default=None, description="Filter to a single calendar date"),
    user_id: Optional[int] = Query(default=None),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator", "viewer")),
):
    return api_list_attendance(day, user_id, limit, db, _admin)

# 6. GET /unknown
from app.api.logs import list_unknown as api_list_unknown
@app.get("/unknown", response_model=List[UnknownFaceOut], tags=["root-api"])
def root_list_unknown(
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator", "viewer")),
):
    return api_list_unknown(limit, db, _admin)

# 7. POST /send-alert
from app.api.logs import resend_alert as api_resend_alert
@app.post("/send-alert", tags=["root-api"])
async def root_send_alert(
    unknown_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator")),
):
    return await api_resend_alert(unknown_id, db, _admin)

# 8. POST /retrain
from app.api.users import trigger_retrain as api_trigger_retrain
@app.post("/retrain", tags=["root-api"])
def root_trigger_retrain(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator")),
):
    return api_trigger_retrain(background_tasks, db, _admin)

# 9. GET /cameras
from app.schemas.auth import CameraOut
from app.api.cameras import list_cameras as api_list_cameras
@app.get("/cameras", response_model=List[CameraOut], tags=["root-api"])
def root_list_cameras(
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator", "viewer")),
):
    return api_list_cameras(db, _admin)

# 10. POST /camera/start
from app.api.cameras import start_camera as api_start_camera
@app.post("/camera/start", tags=["root-api"])
def root_start_camera(
    camera_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator")),
):
    return api_start_camera(camera_id, db, _admin)

# 11. POST /camera/stop
from app.api.cameras import stop_camera as api_stop_camera
@app.post("/camera/stop", tags=["root-api"])
def root_stop_camera(
    camera_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator")),
):
    return api_stop_camera(camera_id, db, _admin)


# 12. POST /search
from app.api.users import search_face as api_search_face
@app.post("/search", tags=["root-api"])
async def root_search_face(
    file: UploadFile = File(..., description="JPEG/PNG image to search"),
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator", "viewer")),
):
    return await api_search_face(file, db, _admin)
