from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    EmployeeID: str
    FullName: str
    Department: Optional[str] = None
    Email: Optional[EmailStr] = None
    TelegramID: Optional[str] = None
    Role: str = "employee"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    UserID: int
    EmployeeID: str
    FullName: str
    Department: Optional[str]
    Email: Optional[str]
    Status: str
    Role: str
    CreatedDate: datetime


class UserRegisterResponse(BaseModel):
    user: UserOut
    embeddings_captured: int
