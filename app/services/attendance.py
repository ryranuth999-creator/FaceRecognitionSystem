"""
Core business logic for a single authentication attempt:

  Camera frame -> detect face -> embedding -> compare to DB
      -> match?  -> yes -> create Attendance + LoginLog (success)
                -> no  -> save snapshot, create UnknownFace record,
                          fire Telegram + Email alerts

This module is used by both the FastAPI endpoint (app/api/auth.py)
and the standalone live-recognition script (training/register_face.py
companion, see README) so the logic only lives in one place.
"""
import logging
import uuid
from datetime import datetime, time, date
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.face.detector import crop_face, detect_faces, get_embeddings
from app.face.recognizer import identify
from app.models.log import Attendance, LoginLog, UnknownFace
from app.notifications.email import send_unknown_person_email
from app.notifications.telegram import send_unknown_person_alert
from app.schemas.auth import FaceLoginResponse

logger = logging.getLogger(__name__)

# Track the last alert time per (camera_id, alert_type) to avoid spamming
_last_alert_sent = {}


async def _send_alerts_bg(
    unknown_id: int,
    photo_path: str,
    camera_name: str,
    confidence: float,
    timestamp: str,
    ip_address: str,
    is_spoof: bool,
    db_session_factory,
):
    if is_spoof:
        alert_title = "🚨 *Warning - Spoofing Attack Detected*"
        telegram_ok = await send_unknown_person_alert(
            photo_path=photo_path,
            camera_name=camera_name,
            confidence=confidence,
            timestamp=timestamp,
            custom_title=alert_title,
        )
        email_ok = await send_unknown_person_email(
            photo_path=photo_path,
            camera_name=camera_name,
            confidence=confidence,
            timestamp=timestamp,
            ip_address=ip_address,
            custom_title="⚠ Spoofing Attack Detected",
        )
    else:
        telegram_ok = await send_unknown_person_alert(
            photo_path=photo_path,
            camera_name=camera_name,
            confidence=confidence,
            timestamp=timestamp,
        )
        email_ok = await send_unknown_person_email(
            photo_path=photo_path,
            camera_name=camera_name,
            confidence=confidence,
            timestamp=timestamp,
            ip_address=ip_address,
        )

    db = db_session_factory()
    try:
        record = db.query(UnknownFace).filter(UnknownFace.UnknownID == unknown_id).first()
        if record:
            record.AlertSent = telegram_ok
            record.EmailSent = email_ok
            db.commit()
    except Exception as e:
        logger.error(f"Failed to update alert status in database: {e}")
        db.rollback()
    finally:
        db.close()


def _save_snapshot(bgr_frame: np.ndarray, prefix: str) -> str:
    out_dir = Path(settings.UNKNOWN_FACE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.jpg"
    path = out_dir / filename
    cv2.imwrite(str(path), bgr_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return str(path)


async def authenticate_frame(
    db: Session,
    bgr_frame: np.ndarray,
    camera_id: str,
    ip_address: str = "N/A",
    background_tasks = None,
) -> FaceLoginResponse:
    """Run the full detect -> embed -> compare -> log -> alert pipeline
    on a single camera frame and return the outcome."""
    rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
    boxes = detect_faces(rgb)

    if not boxes:
        return FaceLoginResponse(authenticated=False, message="No face detected in frame.")

    # Sort boxes by area descending so the largest face (closest to camera) is at index 0
    boxes = sorted(boxes, key=lambda b: (b[2] - b[0]) * (b[1] - b[3]), reverse=True)

    embeddings = get_embeddings(rgb, boxes)
    # Use the largest face in frame (closest to camera) as the probe.
    probe = embeddings[0]
    probe_box = boxes[0]

    now = datetime.now()

    # ---------- Passive Anti-Spoofing Check ----------
    if settings.ANTISPOOFING_ENABLED:
        from app.face.antispoofing import verify_liveness
        is_live, liveness_score = verify_liveness(bgr_frame, probe_box)
        if not is_live:
            # Presentation Attack (spoofing) detected!
            annotated_frame = bgr_frame.copy()
            top, right, bottom, left = probe_box
            cv2.rectangle(annotated_frame, (left, top), (right, bottom), (0, 0, 255), 2)
            cv2.putText(
                annotated_frame,
                "SPOOFING DETECTED",
                (left, max(15, top - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 255),
                1,
                cv2.LINE_AA,
            )
            snapshot_path = _save_snapshot(annotated_frame, prefix="spoof")
            
            # Retrieve Location from Camera
            from app.models.user import Camera
            camera = db.query(Camera).filter(Camera.CameraID == camera_id).first()
            location = camera.Location if camera else "Unknown"
            camera_name = camera.CameraName if camera else camera_id
            
            timestamp_str = now.strftime("%Y-%m-%d %H:%M")
            alert_title = "🚨 *Warning - Spoofing Attack Detected*"
            
            # Cooldown logic for spoofing alert
            last_alert = _last_alert_sent.get((camera_id, "spoof"))
            should_alert = last_alert is None or (now - last_alert).total_seconds() >= settings.ALERT_COOLDOWN_SECONDS

            unknown = UnknownFace(
                Photo=snapshot_path,
                Time=now,
                Confidence=liveness_score,
                CameraID=camera_id,
                Location=location,
                AlertSent=False,
                EmailSent=False,
            )
            db.add(unknown)
            db.commit()
            db.refresh(unknown)

            if should_alert:
                _last_alert_sent[(camera_id, "spoof")] = now
                if background_tasks:
                    from app.core.database import SessionLocal
                    background_tasks.add_task(
                        _send_alerts_bg,
                        unknown_id=unknown.UnknownID,
                        photo_path=snapshot_path,
                        camera_name=camera_name,
                        confidence=liveness_score,
                        timestamp=timestamp_str,
                        ip_address=ip_address,
                        is_spoof=True,
                        db_session_factory=SessionLocal,
                    )
                else:
                    telegram_ok = await send_unknown_person_alert(
                        photo_path=snapshot_path,
                        camera_name=camera_name,
                        confidence=liveness_score,
                        timestamp=timestamp_str,
                        custom_title=alert_title,
                    )
                    email_ok = await send_unknown_person_email(
                        photo_path=snapshot_path,
                        camera_name=camera_name,
                        confidence=liveness_score,
                        timestamp=timestamp_str,
                        ip_address=ip_address,
                        custom_title="⚠ Spoofing Attack Detected",
                    )
                    unknown.AlertSent = telegram_ok
                    unknown.EmailSent = email_ok
                    db.commit()
            else:
                logger.info("Skipping spoofing alert for camera %s due to cooldown.", camera_id)
            
            return FaceLoginResponse(
                authenticated=False,
                confidence=liveness_score,
                message="Access denied: Spoofing attempt detected.",
            )

    result = identify(db, np.array(probe))

    if result.matched and result.user is not None:
        snapshot_path = _save_snapshot(bgr_frame, prefix=f"user{result.user.UserID}")

        db.add(
            LoginLog(
                UserID=result.user.UserID,
                LoginTime=now,
                Result="success",
                Confidence=result.confidence,
                IPAddress=ip_address,
                CameraID=camera_id,
                PhotoPath=snapshot_path,
            )
        )

        current_time = now.time()
        today_start = datetime.combine(now.date(), time.min)
        today_end = datetime.combine(now.date(), time.max)

        existing_attendance = db.query(Attendance).filter(
            Attendance.UserID == result.user.UserID,
            Attendance.CheckIn >= today_start,
            Attendance.CheckIn <= today_end
        ).first()

        if not existing_attendance:
            existing_attendance = db.query(Attendance).filter(
                Attendance.UserID == result.user.UserID,
                Attendance.CheckOut >= today_start,
                Attendance.CheckOut <= today_end
            ).first()

        message = f"Access granted for {result.user.FullName}."

        if time(7, 0) <= current_time <= time(16, 0):
            if not existing_attendance:
                db.add(
                    Attendance(
                        UserID=result.user.UserID,
                        CheckIn=now,
                        Confidence=result.confidence,
                        CameraID=camera_id,
                        Photo=snapshot_path,
                    )
                )
                message = f"Check-in successful for {result.user.FullName}."
            else:
                message = f"Already checked in today, {result.user.FullName}."
        elif time(17, 0) <= current_time <= time(19, 0):
            if existing_attendance:
                existing_attendance.CheckOut = now
                message = f"Check-out successful for {result.user.FullName}."
            else:
                db.add(
                    Attendance(
                        UserID=result.user.UserID,
                        CheckIn=None,
                        CheckOut=now,
                        Confidence=result.confidence,
                        CameraID=camera_id,
                        Photo=snapshot_path,
                    )
                )
                message = f"Check-out successful (no check-in found) for {result.user.FullName}."
        else:
            message = f"Scan successful, {result.user.FullName}, but outside check-in/out hours."

        db.commit()

        return FaceLoginResponse(
            authenticated=True,
            user_id=result.user.UserID,
            full_name=result.user.FullName,
            confidence=result.confidence,
            message=message,
        )

    # ---- Unknown person path ----
    annotated_frame = bgr_frame.copy()
    top, right, bottom, left = probe_box
    cv2.rectangle(annotated_frame, (left, top), (right, bottom), (0, 0, 255), 2)
    cv2.putText(
        annotated_frame,
        "UNKNOWN PERSON",
        (left, max(15, top - 5)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 0, 255),
        1,
        cv2.LINE_AA,
    )
    snapshot_path = _save_snapshot(annotated_frame, prefix="unknown")

    if result.user is not None:
        # A registered LoginLog "failed" attempt tied to the closest (but
        # insufficiently confident) known user, for audit purposes.
        db.add(
            LoginLog(
                UserID=result.user.UserID,
                LoginTime=now,
                Result="failed",
                Confidence=result.confidence,
                IPAddress=ip_address,
                CameraID=camera_id,
                PhotoPath=snapshot_path,
            )
        )

    # Retrieve Location from Camera
    from app.models.user import Camera
    camera = db.query(Camera).filter(Camera.CameraID == camera_id).first()
    location = camera.Location if camera else "Unknown"
    camera_name = camera.CameraName if camera else camera_id

    timestamp_str = now.strftime("%Y-%m-%d %H:%M")
    # Cooldown logic for unknown face alert
    last_alert = _last_alert_sent.get((camera_id, "unknown"))
    should_alert = last_alert is None or (now - last_alert).total_seconds() >= settings.ALERT_COOLDOWN_SECONDS

    unknown = UnknownFace(
        Photo=snapshot_path,
        Time=now,
        Confidence=result.confidence,
        CameraID=camera_id,
        Location=location,
        AlertSent=False,
        EmailSent=False,
    )
    db.add(unknown)
    db.commit()
    db.refresh(unknown)

    if should_alert:
        _last_alert_sent[(camera_id, "unknown")] = now
        if background_tasks:
            from app.core.database import SessionLocal
            background_tasks.add_task(
                _send_alerts_bg,
                unknown_id=unknown.UnknownID,
                photo_path=snapshot_path,
                camera_name=camera_name,
                confidence=result.confidence,
                timestamp=timestamp_str,
                ip_address=ip_address,
                is_spoof=False,
                db_session_factory=SessionLocal,
            )
        else:
            telegram_ok = await send_unknown_person_alert(
                photo_path=snapshot_path, camera_name=camera_name, confidence=result.confidence, timestamp=timestamp_str
            )
            email_ok = await send_unknown_person_email(
                photo_path=snapshot_path,
                camera_name=camera_name,
                confidence=result.confidence,
                timestamp=timestamp_str,
                ip_address=ip_address,
            )
            unknown.AlertSent = telegram_ok
            unknown.EmailSent = email_ok
            db.commit()
    else:
        logger.info("Skipping unknown face alert for camera %s due to cooldown.", camera_id)

    return FaceLoginResponse(
        authenticated=False,
        confidence=result.confidence,
        message="Unknown person detected. Security has been alerted via Telegram/Email.",
    )
