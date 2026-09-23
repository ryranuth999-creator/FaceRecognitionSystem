from fastapi import APIRouter, Depends
from app.api.deps import require_role
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
def get_app_settings(_admin=Depends(require_role("admin"))):
    return {
        "FACE_MATCH_THRESHOLD": settings.FACE_MATCH_THRESHOLD,
        "FACE_MODEL": settings.FACE_MODEL,
        "UNKNOWN_FACE_DIR": settings.UNKNOWN_FACE_DIR,
        "EMBEDDINGS_PER_USER": settings.EMBEDDINGS_PER_USER,
        "ANTISPOOFING_ENABLED": settings.ANTISPOOFING_ENABLED,
        "TELEGRAM_ENABLED": settings.TELEGRAM_ENABLED,
        "TELEGRAM_BOT_TOKEN": settings.TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": settings.TELEGRAM_CHAT_ID,
        "EMAIL_ENABLED": settings.EMAIL_ENABLED,
        "SMTP_HOST": settings.SMTP_HOST,
        "SMTP_PORT": settings.SMTP_PORT,
        "SMTP_USERNAME": settings.SMTP_USERNAME,
        "SMTP_FROM": settings.SMTP_FROM,
        "ALERT_EMAIL_RECIPIENTS": settings.ALERT_EMAIL_RECIPIENTS,
    }


@router.post("/settings")
def update_app_settings(data: dict, _admin=Depends(require_role("admin"))):
    # Update settings fields in memory
    for key, val in data.items():
        if hasattr(settings, key):
            # Apply appropriate types
            if key == "FACE_MATCH_THRESHOLD":
                val = float(val)
            elif key in ("EMBEDDINGS_PER_USER", "SMTP_PORT"):
                val = int(val)
            elif key in ("TELEGRAM_ENABLED", "EMAIL_ENABLED", "ANTISPOOFING_ENABLED"):
                val = bool(val)
            setattr(settings, key, val)
    return {"detail": "Settings updated successfully"}
