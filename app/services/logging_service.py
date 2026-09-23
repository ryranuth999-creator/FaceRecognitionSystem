"""
Helper queries for the admin dashboard / reporting endpoints
(GET /logs, /attendance, /unknown, dashboard statistics, etc).
Kept separate from attendance.py (which handles the *write* path
during a live recognition event) to keep read/write concerns apart.
"""
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.log import Attendance, LoginLog, UnknownFace
from app.models.user import User


def get_attendance(db: Session, day: Optional[date] = None, user_id: Optional[int] = None, limit: int = 200) -> List[Attendance]:
    query = db.query(Attendance)
    if user_id:
        query = query.filter(Attendance.UserID == user_id)
    if day:
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        query = query.filter(Attendance.CheckIn >= start, Attendance.CheckIn < end)
    return query.order_by(Attendance.CheckIn.desc()).limit(limit).all()


def get_login_logs(db: Session, result: Optional[str] = None, limit: int = 200) -> List[LoginLog]:
    query = db.query(LoginLog)
    if result:
        query = query.filter(LoginLog.Result == result)
    return query.order_by(LoginLog.LoginTime.desc()).limit(limit).all()


def get_unknown_faces(db: Session, limit: int = 200) -> List[UnknownFace]:
    return db.query(UnknownFace).order_by(UnknownFace.Time.desc()).limit(limit).all()


def dashboard_stats(db: Session) -> dict:
    today = datetime.now().date()
    start = datetime.combine(today, datetime.min.time())
    end = start + timedelta(days=1)

    total_users = db.query(func.count(User.UserID)).filter(User.Status == "active").scalar()
    today_attendance = (
        db.query(func.count(Attendance.AttendanceID))
        .filter(Attendance.CheckIn >= start, Attendance.CheckIn < end)
        .scalar()
    )
    today_unknown = (
        db.query(func.count(UnknownFace.UnknownID))
        .filter(UnknownFace.Time >= start, UnknownFace.Time < end)
        .scalar()
    )
    failed_logins_today = (
        db.query(func.count(LoginLog.LogID))
        .filter(LoginLog.Result == "failed", LoginLog.LoginTime >= start, LoginLog.LoginTime < end)
        .scalar()
    )

    return {
        "total_registered_users": total_users or 0,
        "today_attendance_count": today_attendance or 0,
        "today_unknown_faces": today_unknown or 0,
        "today_failed_logins": failed_logins_today or 0,
    }
