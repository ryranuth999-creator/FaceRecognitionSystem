# Face Recognition Authentication System

Face-recognition based authentication and attendance logging, backed by
SQL Server, with Telegram + Email alerts whenever an unrecognized
("unknown") person is detected.

Built to match the attached project specification: FastAPI + OpenCV +
face embeddings + SQL Server, with a REST API, admin dashboard, and
standalone camera scripts.

## 1. Tech stack (what's actually implemented)

| Layer | Used here | Assignment's suggestion | Why the substitution |
|---|---|---|---|
| API | FastAPI | FastAPI | ✅ same |
| Face detection | `face_recognition` (dlib HOG) | YOLOv8-Face / RetinaFace | CPU-only, pip-installable, no model download/training needed for a laptop webcam demo |
| Face recognition | `face_recognition` (dlib ResNet, 128-d) | InsightFace (ArcFace, 512-d) | Same reasoning — zero GPU/model-zoo setup required. Swap instructions below. |
| Database | SQL Server (via SQLAlchemy + pyodbc) | SQL Server | ✅ same. SQLite supported as a zero-install dev fallback. |
| Notifications | Telegram Bot API + SMTP (aiosmtplib) | Telegram + Email | ✅ same |
| Auth (dashboard/API) | JWT (python-jose) + bcrypt | JWT + OAuth2 | ✅ same |
| Admin dashboard | FastAPI + Jinja2 server-rendered page | FastAPI or React+FastAPI | Kept pure-Python per "fullstack Python developer" request |

Everything below the API boundary (`app/face/detector.py`,
`app/face/recognizer.py`) is isolated behind two functions
(`detect_faces`, `get_embeddings`) so you can swap in InsightFace
later without touching the API, services, or database layers.

### Swapping in InsightFace (optional, for higher accuracy / GPU use)

1. `pip install insightface onnxruntime` (or `onnxruntime-gpu`)
2. Rewrite `app/face/detector.py`'s `detect_faces`/`get_embeddings` to
   call `insightface.app.FaceAnalysis` and return the same
   `(boxes, embeddings)` shapes (embeddings become 512-d).
3. Bump `ModelVersion` in `FaceEmbedding` rows and run
   `training/retrain.py` to recompute all stored embeddings — 128-d
   and 512-d vectors are **not** comparable, so mixing them silently
   breaks matching.

## 2. Project structure

```
FaceRecognitionSystem/
├── app/
│   ├── api/            # FastAPI routers (auth, users, attendance, logs, cameras, dashboard)
│   ├── core/            # config, DB engine/session, JWT + password hashing
│   ├── face/            # detector, recognizer, camera helpers
│   ├── models/          # SQLAlchemy ORM models (Users, FaceEmbeddings, Attendance, LoginLogs, UnknownFaces, Cameras)
│   ├── notifications/   # Telegram + Email alert senders
│   ├── services/        # business logic: attendance.py (recognition pipeline), logging_service.py (reports)
│   ├── schemas/         # Pydantic request/response models
│   ├── static/unknown_faces/  # saved snapshots of unknown-person events
│   ├── templates/       # dashboard.html
│   └── main.py          # FastAPI app entrypoint
├── training/
│   ├── register_face.py     # webcam enrollment CLI (writes straight to DB)
│   ├── retrain.py           # recompute embeddings after a model upgrade
│   └── live_recognition.py  # continuous webcam loop -> POSTs to /api/auth/login-face
├── sql/schema.sql       # hand-authored SQL Server DDL (optional; init_db() also auto-creates tables)
├── tests/test_recognizer.py
├── requirements.txt
├── .env.example
└── README.md
```

## 3. Setup

### 3.1 Prerequisites

- Python 3.10+
- A webcam (for enrollment / live recognition scripts)
- SQL Server 2019+ (or use `DB_BACKEND=sqlite` for local dev without SQL Server)
- **ODBC Driver 17 or 18 for SQL Server** installed on the host machine (required by `pyodbc`)
- `cmake` + a C++ compiler on your system (needed to build `dlib`, a dependency of `face-recognition`) — on Windows, install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/); on macOS, `brew install cmake`; on Ubuntu, `sudo apt install cmake build-essential`

### 3.2 Install

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: DB credentials, Telegram bot token, SMTP credentials
```

### 3.3 Database

**Option A — SQL Server (production):**
```bash
# create the database first, e.g. via SSMS or:
sqlcmd -S localhost -U sa -P "YourStrong@Passw0rd" -Q "CREATE DATABASE FaceRecognitionDB"
# tables are auto-created on first API startup (init_db()), or run manually:
sqlcmd -S localhost -U sa -P "YourStrong@Passw0rd" -d FaceRecognitionDB -i sql/schema.sql
```
Set `DB_BACKEND=mssql` in `.env` (default).

**Option B — SQLite (quick local testing, no SQL Server needed):**
```bash
# in .env:
DB_BACKEND=sqlite
```

### 3.4 Telegram bot setup

1. Talk to [@BotFather](https://t.me/BotFather) on Telegram, run `/newbot`, copy the token into `TELEGRAM_BOT_TOKEN`.
2. Send any message to your new bot, then visit
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the
   `chat.id` value into `TELEGRAM_CHAT_ID`.
3. Set `TELEGRAM_ENABLED=true`.

### 3.5 Email (SMTP) setup

Fill in `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`
(for Gmail, use an [App Password](https://myaccount.google.com/apppasswords),
not your normal password), `SMTP_FROM`, and `ALERT_EMAIL_RECIPIENTS`
(comma-separated). Set `EMAIL_ENABLED=true`.

## 4. Running

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger API docs: http://localhost:8000/docs
- Admin dashboard: http://localhost:8000/dashboard

### 4.1 Enroll a user (two ways)

**Via API** (e.g. from a phone/kiosk app or Swagger UI) — `POST /api/register` with
`multipart/form-data`: `employee_id`, `full_name`, `department`,
`email`, `telegram_id`, and 10-30 `files` (JPEG/PNG face photos).

**Via webcam CLI:**
```bash
python training/register_face.py --employee-id E001 --name "Jane Doe" \
    --department Engineering --email jane@example.com --count 20
```

### 4.2 Authenticate / log attendance

**Via webcam CLI (continuous loop):**
```bash
python training/live_recognition.py --server http://localhost:8000 --camera-id CAM-01
```

**Via API directly:** `POST /api/auth/login-face` with a single image
file + `camera_id` form field. Response tells you whether the person
was recognized, and (if not) that Telegram/email alerts were fired.

### 4.3 Admin login (for protected endpoints)

Protected endpoints (`/api/users`, `/api/logs`, `/api/attendance`,
`/api/unknown`, `/api/cameras`) require a JWT from
`POST /api/auth/token` (OAuth2 password flow). Create an admin user
first (e.g. via a Python shell using `app.core.security.hash_password`
and inserting a `User` row with `Role="admin"` and a
`HashedPassword`), then:

```bash
curl -X POST http://localhost:8000/api/auth/token \
  -d "username=admin001&password=yourpassword"
```

## 5. Recognition pipeline (as implemented)

```
Camera frame (JPEG upload or webcam grab)
      │
      ▼
OpenCV decode → RGB conversion
      │
      ▼
face_recognition.face_locations()   (face detection)
      │
      ▼
face_recognition.face_encodings()   (128-d embedding)
      │
      ▼
Compare probe embedding to every enrolled embedding in SQL Server
(Euclidean distance → confidence score 0-1)
      │
      ├─ confidence ≥ FACE_MATCH_THRESHOLD (default 0.70)
      │      → INSERT Attendance + LoginLog(success)
      │      → return "Access granted"
      │
      └─ confidence < threshold ("unknown person")
             → save snapshot to app/static/unknown_faces/
             → INSERT UnknownFace row
             → send Telegram alert (photo + caption)
             → send HTML email alert (photo attached)
             → return "Unknown person detected"
```

## 6. Security notes

- Passwords are hashed with bcrypt (`passlib`); never stored in plaintext.
- API endpoints beyond registration/login are protected by JWT + role checks (`admin`/`operator`/`viewer`).
- Face embeddings are stored as opaque binary blobs — for production, consider column-level encryption (e.g. SQL Server Always Encrypted) since embeddings are biometric data subject to privacy regulations (GDPR/BIPA depending on jurisdiction).
- Run behind HTTPS in production (the assignment recommends a self-signed cert for internal deployments; use a real CA-signed cert if internet-facing).
- Rate-limit `/api/auth/login-face` in production (e.g. via a reverse proxy) to prevent brute-force probing.

## 7. What's not implemented (flagged as "Optional AI Features" / later phases in the spec)

- Liveness detection / anti-spoofing (blink/head-movement/3D depth, or dedicated models like Silent-Face-Anti-Spoofing) — the current system will accept a printed photo or phone screen as a face. Add this before using the system for real physical access control.
- React admin frontend (a working server-rendered dashboard is included instead).
- Face-search-by-upload and analytics dashboards beyond the basic stats included.

These map to Phases 7-8 in the assignment's development roadmap and
are natural next steps once the core pipeline (Phases 1-6, all
implemented here) is validated.

## 8. Tests

```bash
pip install pytest
DB_BACKEND=sqlite pytest tests/ -v
```

The included tests validate the matching/threshold math using SQLite
and synthetic embeddings — they don't require a camera, SQL Server,
Telegram, or SMTP credentials.
