from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    UserID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    EmployeeID: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    FullName: Mapped[str] = mapped_column(String(150))
    Department: Mapped[str] = mapped_column(String(100), nullable=True)
    Email: Mapped[str] = mapped_column(String(150), nullable=True)
    TelegramID: Mapped[str] = mapped_column(String(50), nullable=True)
    Role: Mapped[str] = mapped_column(String(20), default="employee")  # admin/operator/viewer/employee
    Status: Mapped[str] = mapped_column(String(20), default="active")  # active/disabled
    HashedPassword: Mapped[str] = mapped_column(String(255), nullable=True)  # for dashboard login (admins)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    embeddings = relationship("FaceEmbedding", back_populates="user", cascade="all, delete-orphan")
    attendance_records = relationship("Attendance", back_populates="user", cascade="all, delete-orphan")
    login_logs = relationship("LoginLog", back_populates="user", cascade="all, delete-orphan")


class Camera(Base):
    __tablename__ = "Cameras"

    CameraID: Mapped[str] = mapped_column(String(50), primary_key=True)
    CameraName: Mapped[str] = mapped_column(String(100))
    IP: Mapped[str] = mapped_column(String(50), nullable=True)
    Location: Mapped[str] = mapped_column(String(150), nullable=True)
    Status: Mapped[str] = mapped_column(String(20), default="offline")  # online/offline
