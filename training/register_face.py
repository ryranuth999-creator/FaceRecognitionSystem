"""
Standalone enrollment tool: opens the laptop webcam, captures N face
images, and registers a new user directly to the database (bypassing
the REST API — useful for the initial admin setup at a kiosk/PC that
doesn't have network access to the API server).

Usage:
    python training/register_face.py --employee-id E001 --name "Jane Doe" \
        --department "Engineering" --email jane@example.com --count 20

For registering via the running API instead (recommended for normal
operation), POST multipart images to /api/register — see README.md.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))  # allow `import app.*`

import cv2

from app.core.database import db_session, init_db
from app.face.camera import bgr_to_rgb, capture_frame, open_camera
from app.face.detector import detect_faces, get_embeddings, ACTIVE_MODEL_NAME
from app.models.face_encoding import FaceEmbedding
from app.models.user import User


def main():
    parser = argparse.ArgumentParser(description="Enroll a new user's face via webcam")
    parser.add_argument("--employee-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--department", default=None)
    parser.add_argument("--email", default=None)
    parser.add_argument("--telegram-id", default=None)
    parser.add_argument("--count", type=int, default=20, help="Number of embeddings to capture")
    parser.add_argument("--camera-index", type=int, default=0)
    args = parser.parse_args()

    init_db()

    with db_session() as db:
        existing = db.query(User).filter(User.EmployeeID == args.employee_id).first()
        if existing:
            print(f"Employee {args.employee_id} is already registered (UserID={existing.UserID}). Aborting.")
            return

        user = User(
            EmployeeID=args.employee_id,
            FullName=args.name,
            Department=args.department,
            Email=args.email,
            TelegramID=args.telegram_id,
        )
        db.add(user)
        db.flush()
        user_id = user.UserID

        captured = 0
        print(f"Look at the camera. Capturing {args.count} good frames... (press 'q' to abort)")
        with open_camera(args.camera_index) as cap:
            while captured < args.count:
                frame = capture_frame(cap)
                rgb = bgr_to_rgb(frame)
                boxes = detect_faces(rgb)

                display = frame.copy()
                for (top, right, bottom, left) in boxes:
                    cv2.rectangle(display, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.putText(
                    display, f"Captured {captured}/{args.count}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
                )
                cv2.imshow("Enrollment - press q to stop early", display)

                if len(boxes) == 1:
                    embeddings = get_embeddings(rgb, boxes)
                    if embeddings:
                        db.add(
                            FaceEmbedding(
                                UserID=user_id,
                                EmbeddingVector=FaceEmbedding.encode_vector(embeddings[0].tolist()),
                                Model=ACTIVE_MODEL_NAME,
                            )
                        )

                        captured += 1
                        time.sleep(0.3)  # slight delay so consecutive frames aren't near-duplicates

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        cv2.destroyAllWindows()

        if captured == 0:
            raise RuntimeError("No usable face captures — rolling back registration.")

    print(f"Done. Registered {args.name} ({args.employee_id}) with {captured} face embeddings.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
