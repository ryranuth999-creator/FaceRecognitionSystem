from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.schemas.auth import AttendanceOut
from app.services.logging_service import get_attendance

router = APIRouter(prefix="/api", tags=["attendance"])


@router.get("/attendance", response_model=List[AttendanceOut])
def list_attendance(
    day: Optional[date] = Query(default=None, description="Filter to a single calendar date"),
    user_id: Optional[int] = Query(default=None),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator", "viewer")),
):
    return get_attendance(db, day=day, user_id=user_id, limit=limit)
