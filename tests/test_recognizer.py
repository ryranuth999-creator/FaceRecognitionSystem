"""
Lightweight unit tests that don't require a real camera, SQL Server,
Telegram, or SMTP — they exercise the matching math and API wiring
using SQLite + mocked embeddings.

Run with:
    DB_BACKEND=sqlite pytest tests/ -v
"""
import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.face.recognizer import identify
from app.models.face_encoding import FaceEmbedding
from app.models.user import User


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _make_user_with_embedding(db, employee_id: str, vector: list[float]) -> User:
    user = User(EmployeeID=employee_id, FullName=f"Test {employee_id}")
    db.add(user)
    db.flush()
    db.add(FaceEmbedding(UserID=user.UserID, EmbeddingVector=FaceEmbedding.encode_vector(vector)))
    db.commit()
    return user


def test_identify_matches_known_face(db_session):
    vector = [0.1] * 512
    user = _make_user_with_embedding(db_session, "E001", vector)

    probe = np.array(vector)  # identical vector -> cosine similarity 1.0 -> confidence 1.0
    result = identify(db_session, probe, threshold=0.70)

    assert result.matched is True
    assert result.user.UserID == user.UserID
    assert result.confidence == pytest.approx(1.0, abs=0.01)


def test_identify_rejects_unknown_face(db_session):
    vector = [0.1] * 512
    _make_user_with_embedding(db_session, "E002", vector)

    probe = np.array([0.5 if i % 2 == 0 else -0.5 for i in range(512)])  # orthogonal -> similarity 0.0 -> low confidence
    result = identify(db_session, probe, threshold=0.70)

    assert result.matched is False


def test_identify_with_no_enrolled_users(db_session):
    probe = np.zeros(512)
    result = identify(db_session, probe, threshold=0.70)
    assert result.matched is False
    assert result.user is None


@pytest.mark.anyio
async def test_authenticate_frame_logs_date_time_and_status(db_session, monkeypatch):
    from app.services.attendance import authenticate_frame
    from app.models.log import LoginLog
    import numpy as np

    vector = [0.1] * 512
    user = _make_user_with_embedding(db_session, "E003", vector)

    # Mock face detection and embedding generation to return our registered user's face
    monkeypatch.setattr("app.services.attendance.detect_faces", lambda rgb: [(0, 10, 10, 0)])
    monkeypatch.setattr("app.services.attendance.get_embeddings", lambda rgb, boxes: [np.array(vector)])
    monkeypatch.setattr("app.services.attendance._save_snapshot", lambda frame, prefix: "mock_path.jpg")
    monkeypatch.setattr("app.face.antispoofing.verify_liveness", lambda frame, box: (True, 1.0))
    
    async def mock_alert(**kw):
        return True
    
    monkeypatch.setattr("app.services.attendance.send_unknown_person_alert", mock_alert)
    monkeypatch.setattr("app.services.attendance.send_unknown_person_email", mock_alert)

    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    response = await authenticate_frame(db_session, dummy_frame, camera_id="CAM-01", ip_address="127.0.0.1")

    assert response.authenticated is True
    assert response.user_id == user.UserID

    # Query the LoginLog to verify the new fields
    log = db_session.query(LoginLog).filter(LoginLog.UserID == user.UserID).first()
    assert log is not None
    assert log.Result == "success"
    assert log.LoginTime is not None
    assert log.IPAddress == "127.0.0.1"
    assert log.CameraID == "CAM-01"
    assert log.PhotoPath == "mock_path.jpg"


@pytest.mark.anyio
async def test_authenticate_frame_logs_unknown_face_with_location(db_session, monkeypatch):
    from app.services.attendance import authenticate_frame
    from app.models.log import UnknownFace
    from app.models.user import Camera
    import numpy as np

    # Seed the camera location
    camera = Camera(CameraID="CAM-02", CameraName="Test Camera", Location="Main Gate", Status="online")
    db_session.add(camera)
    db_session.commit()

    # Mock face detection and embedding generation to return an unknown face
    monkeypatch.setattr("app.services.attendance.detect_faces", lambda rgb: [(0, 10, 10, 0)])
    monkeypatch.setattr("app.services.attendance.get_embeddings", lambda rgb, boxes: [np.array([5.0] * 512)])
    monkeypatch.setattr("app.services.attendance._save_snapshot", lambda frame, prefix: "unknown_mock.jpg")
    monkeypatch.setattr("app.face.antispoofing.verify_liveness", lambda frame, box: (True, 1.0))

    # Track the order of execution for sending alerts first
    call_order = []

    async def mock_alert(**kw):
        call_order.append("alert")
        return True

    async def mock_email(**kw):
        call_order.append("email")
        return True

    monkeypatch.setattr("app.services.attendance.send_unknown_person_alert", mock_alert)
    monkeypatch.setattr("app.services.attendance.send_unknown_person_email", mock_email)

    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    response = await authenticate_frame(db_session, dummy_frame, camera_id="CAM-02", ip_address="127.0.0.1")

    assert response.authenticated is False

    # Check alert order: alert and email must have run before we insert/commit into SQL logs (which is after function return here)
    assert "alert" in call_order
    assert "email" in call_order

    # Query the UnknownFace log to verify fields
    record = db_session.query(UnknownFace).filter(UnknownFace.Photo == "unknown_mock.jpg").first()
    assert record is not None
    assert record.CameraID == "CAM-02"
    assert record.Location == "Main Gate"
    assert record.Time is not None
    assert record.AlertSent is True
    assert record.EmailSent is True


@pytest.mark.anyio
async def test_alert_cooldown_logic(db_session, monkeypatch):
    from app.services.attendance import authenticate_frame, _last_alert_sent
    from app.core.config import settings
    import numpy as np

    # Reset any previous in-memory state
    _last_alert_sent.clear()
    
    # Mock face detection and embedding generation to return an unknown face
    monkeypatch.setattr("app.services.attendance.detect_faces", lambda rgb: [(0, 10, 10, 0)])
    monkeypatch.setattr("app.services.attendance.get_embeddings", lambda rgb, boxes: [np.array([5.0] * 512)])
    monkeypatch.setattr("app.services.attendance._save_snapshot", lambda frame, prefix: "unknown_cooldown.jpg")
    monkeypatch.setattr("app.face.antispoofing.verify_liveness", lambda frame, box: (True, 1.0))

    alert_calls = 0

    async def mock_alert(**kw):
        nonlocal alert_calls
        alert_calls += 1
        return True

    monkeypatch.setattr("app.services.attendance.send_unknown_person_alert", mock_alert)
    monkeypatch.setattr("app.services.attendance.send_unknown_person_email", mock_alert)

    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    # First attempt: Alert should be sent
    await authenticate_frame(db_session, dummy_frame, camera_id="CAM-03", ip_address="127.0.0.1")
    assert alert_calls == 2  # 1 telegram + 1 email

    # Second attempt immediately after: Alert should be skipped due to cooldown
    await authenticate_frame(db_session, dummy_frame, camera_id="CAM-03", ip_address="127.0.0.1")
    assert alert_calls == 2  # No new calls should be made

    # Change settings to 0 cooldown and test that it fires again
    monkeypatch.setattr(settings, "ALERT_COOLDOWN_SECONDS", 0)
    await authenticate_frame(db_session, dummy_frame, camera_id="CAM-03", ip_address="127.0.0.1")
    assert alert_calls == 4  # Fires again (1 telegram + 1 email)


def test_get_enroll_metadata(db_session):
    from app.api.users import get_enroll_metadata
    from app.models.user import User

    # Initially, with no users (or just admin), next ID should default to E001
    res = get_enroll_metadata(db=db_session)
    assert res["next_employee_id"] == "E001"
    assert "IT" in res["departments"]

    # If we add a user with EmployeeID = ET1113
    u1 = User(EmployeeID="ET1113", FullName="User 1", Department="Research")
    db_session.add(u1)
    db_session.commit()

    res = get_enroll_metadata(db=db_session)
    assert res["next_employee_id"] == "ET1114"
    assert "Research" in res["departments"]
    assert "IT" in res["departments"]

    # If we add a user with a different format like E009
    u2 = User(EmployeeID="E009", FullName="User 2", Department="HR")
    db_session.add(u2)
    db_session.commit()

    res = get_enroll_metadata(db=db_session)
    # The last registered non-admin user is u2 (E009)
    # So next should be E010
    assert res["next_employee_id"] == "E010"


