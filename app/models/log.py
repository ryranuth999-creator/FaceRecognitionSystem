from datetime import date, datetime, time

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Date, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Attendance(Base):
    __tablename__ = "attendance"

    AttendanceID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    UserID: Mapped[int] = mapped_column(ForeignKey("users.UserID", ondelete="CASCADE"))
    CheckIn: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=True)
    CheckOut: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    Confidence: Mapped[float] = mapped_column(Float)
    CameraID: Mapped[str] = mapped_column(String(50), nullable=True)
    Photo: Mapped[str] = mapped_column(String(255), nullable=True)  # stored file path

    user = relationship("User", back_populates="attendance_records")


class LoginLog(Base):
    """Every recognition attempt (success or failure) for known users."""

    __tablename__ = "LoginLogs"

    LogID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    UserID: Mapped[int] = mapped_column(ForeignKey("users.UserID", ondelete="CASCADE"))
    LoginTime: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    Result: Mapped[str] = mapped_column(String(20))  # success/failed
    Confidence: Mapped[float] = mapped_column(Float, nullable=True)
    IPAddress: Mapped[str] = mapped_column(String(50), nullable=True)
    CameraID: Mapped[str] = mapped_column(String(50), nullable=True)
    PhotoPath: Mapped[str] = mapped_column(String(255), nullable=True)

    user = relationship("User", back_populates="login_logs")


class UnknownFace(Base):
    """A face was detected but did not match any registered user
    above the similarity threshold. Triggers Telegram + email alerts."""

    __tablename__ = "UnknownFaces"

    UnknownID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Photo: Mapped[str] = mapped_column(String(255))  # file path to saved snapshot
    Time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    Confidence: Mapped[float] = mapped_column(Float, nullable=True)  # best (still failing) match score
    CameraID: Mapped[str] = mapped_column(String(50), nullable=True)
    Location: Mapped[str] = mapped_column(String(150), nullable=True)
    AlertSent: Mapped[bool] = mapped_column(Boolean, default=False)
    EmailSent: Mapped[bool] = mapped_column(Boolean, default=False)

