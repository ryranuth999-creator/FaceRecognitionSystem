from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminLogin(BaseModel):
    username: str
    password: str


class FaceLoginResponse(BaseModel):
    authenticated: bool
    user_id: Optional[int] = None
    full_name: Optional[str] = None
    confidence: Optional[float] = None
    message: str


class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    AttendanceID: int
    UserID: int
    CheckIn: datetime
    CheckOut: Optional[datetime]
    Confidence: float
    CameraID: Optional[str]
    Photo: Optional[str]


class LoginLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    LogID: int
    UserID: int
    LoginTime: datetime
    Result: str
    Confidence: Optional[float]
    IPAddress: Optional[str]
    CameraID: Optional[str]
    PhotoPath: Optional[str]


class UnknownFaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    UnknownID: int
    Photo: str
    Time: datetime
    Confidence: Optional[float]
    CameraID: Optional[str]
    Location: Optional[str]
    AlertSent: bool
    EmailSent: bool


class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    CameraID: str
    CameraName: str
    IP: Optional[str]
    Location: Optional[str]
    Status: str
