from typing import List

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.config import settings
from app.core.database import get_db
from app.face.detector import get_embeddings, ACTIVE_MODEL_NAME
from app.face.recognizer import invalidate_embeddings_cache
from app.models.face_encoding import FaceEmbedding
from app.models.user import User
from app.schemas.user import UserOut, UserRegisterResponse

router = APIRouter(prefix="/api", tags=["users"])


@router.post("/register", response_model=UserRegisterResponse)
async def register_user(
    employee_id: str = Form(...),
    full_name: str = Form(...),
    department: str = Form(default=None),
    email: str = Form(default=None),
    telegram_id: str = Form(default=None),
    files: List[UploadFile] = File(..., description="10-30 face images from different angles"),
    db: Session = Depends(get_db),
):
    """
    Enroll a new user: creates the User row and captures one
    FaceEmbedding row per usable uploaded image (per assignment
    Module 1: "Capture 10-30 face images -> quality check -> generate
    embeddings -> save").
    """
    existing = db.query(User).filter(User.EmployeeID == employee_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="EmployeeID already registered")

    if len(files) < 1:
        raise HTTPException(status_code=400, detail="At least one face image is required")
    if len(files) > settings.EMBEDDINGS_PER_USER:
        files = files[: settings.EMBEDDINGS_PER_USER]

    user = User(
        EmployeeID=employee_id,
        FullName=full_name,
        Department=department,
        Email=email,
        TelegramID=telegram_id,
    )
    db.add(user)
    db.flush()  # get UserID before commit

    captured = 0
    for upload in files:
        contents = await upload.read()
        npimg = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        if frame is None:
            continue  # skip unreadable/corrupt image (basic quality check)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        embeddings = get_embeddings(rgb)
        if not embeddings:
            continue  # no face detected -> skip (basic quality check)

        db.add(
            FaceEmbedding(
                UserID=user.UserID,
                EmbeddingVector=FaceEmbedding.encode_vector(embeddings[0].tolist()),
                Model=ACTIVE_MODEL_NAME,
            )
        )

        captured += 1

    if captured == 0:
        db.rollback()
        raise HTTPException(status_code=422, detail="No valid faces detected in any uploaded image")

    db.commit()
    invalidate_embeddings_cache()
    db.refresh(user)

    return UserRegisterResponse(user=UserOut.model_validate(user), embeddings_captured=captured)


@router.get("/users/enroll-metadata")
def get_enroll_metadata(db: Session = Depends(get_db), _admin=Depends(require_role("admin", "operator", "viewer"))):
    import re
    # Fetch non-admin users to find the next ID
    users = db.query(User).filter(User.EmployeeID != "admin").order_by(User.UserID.desc()).all()
    
    next_id = "E001"
    for u in users:
        match = re.match(r"^([A-Za-z]+)(\d+)$", u.EmployeeID)
        if match:
            prefix = match.group(1)
            num_str = match.group(2)
            num_val = int(num_str)
            next_num = num_val + 1
            next_id = f"{prefix}{next_num:0{len(num_str)}d}"
            break

    # Fetch unique departments and merge with defaults
    DEFAULT_DEPARTMENTS = ["IT", "HR", "Finance", "Marketing", "Sales", "Operations", "Engineering"]
    db_depts = db.query(User.Department).distinct().all()
    departments = list(DEFAULT_DEPARTMENTS)
    for (dept,) in db_depts:
        if dept and dept not in departments:
            departments.append(dept)

    return {
        "next_employee_id": next_id,
        "departments": departments
    }


@router.get("/users", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _admin=Depends(require_role("admin", "operator", "viewer"))):
    return db.query(User).order_by(User.CreatedDate.desc()).all()


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db), _admin=Depends(require_role("admin", "operator", "viewer"))):
    user = db.query(User).filter(User.UserID == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), _admin=Depends(require_role("admin"))):
    user = db.query(User).filter(User.UserID == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    invalidate_embeddings_cache()
    return {"detail": "User deleted"}


from fastapi import BackgroundTasks
from pathlib import Path
import cv2
import numpy as np
from app.models.face_encoding import FaceEmbedding
from app.face.detector import get_embeddings

def run_retraining_in_background(db_session_factory):
    db = db_session_factory()
    try:
        raw_dir = Path("training/raw_photos")
        if not raw_dir.exists():
            return
        
        for user_dir in raw_dir.iterdir():
            if not user_dir.is_dir():
                continue
            employee_id = user_dir.name
            user = db.query(User).filter(User.EmployeeID == employee_id).first()
            if not user:
                continue
            
            db.query(FaceEmbedding).filter(FaceEmbedding.UserID == user.UserID).delete()
            for image_path in user_dir.glob("*.jpg"):
                frame = cv2.imread(str(image_path))
                if frame is None:
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                embeddings = get_embeddings(rgb)
                if not embeddings:
                    continue
                db.add(
                    FaceEmbedding(
                        UserID=user.UserID,
                        EmbeddingVector=FaceEmbedding.encode_vector(embeddings[0].tolist()),
                        Model=ACTIVE_MODEL_NAME,
                    )
                )
        db.commit()
        invalidate_embeddings_cache()
    except Exception:
        db.rollback()
    finally:
        db.close()

@router.post("/retrain")
def trigger_retrain(background_tasks: BackgroundTasks, db: Session = Depends(get_db), _admin=Depends(require_role("admin", "operator"))):
    from app.core.database import SessionLocal
    background_tasks.add_task(run_retraining_in_background, SessionLocal)
    return {"detail": "Retraining task started in the background."}


from app.face.detector import detect_faces
from app.face.recognizer import identify

@router.post("/search")
async def search_face(
    file: UploadFile = File(..., description="JPEG/PNG image to search"),
    db: Session = Depends(get_db),
    _admin=Depends(require_role("admin", "operator", "viewer")),
):
    """
    Search for a matching employee by uploading their photo.
    Returns the matching user details and similarity confidence score.
    """
    contents = await file.read()
    npimg = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode uploaded image")

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    boxes = detect_faces(rgb)
    if not boxes:
        raise HTTPException(status_code=404, detail="No faces detected in the uploaded image")

    embeddings = get_embeddings(rgb, boxes)
    probe = embeddings[0]

    result = identify(db, np.array(probe))
    if not result.user:
        return {
            "matched": False,
            "confidence": result.confidence,
            "message": "No matching employee found."
        }

    return {
        "matched": result.matched,
        "confidence": result.confidence,
        "user": {
            "UserID": result.user.UserID,
            "EmployeeID": result.user.EmployeeID,
            "FullName": result.user.FullName,
            "Department": result.user.Department,
            "Role": result.user.Role,
            "Status": result.user.Status,
        },
        "message": f"Match found: {result.user.FullName} ({result.confidence * 100:.1f}%)" if result.matched else "Closest guess (below match threshold)"
    }
