"""
Recomputes face embeddings for all enrolled users.

Useful after upgrading the recognition model (e.g. swapping
face_recognition -> InsightFace, see README "Swapping in InsightFace")
since old embeddings computed with a previous model are not compatible
with the new model's vector space.

This script expects raw enrollment photos to still be available on
disk under `training/raw_photos/<EmployeeID>/*.jpg` (a convention you
can enforce in your own capture pipeline; the default register_face.py
above captures straight into the DB and does not keep raw photos, so
adapt as needed for your deployment).
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import cv2

from app.core.database import db_session, init_db
from app.face.detector import get_embeddings, ACTIVE_MODEL_NAME
from app.models.face_encoding import FaceEmbedding
from app.models.user import User

RAW_PHOTOS_DIR = Path(__file__).resolve().parent / "raw_photos"
# Model name imported dynamically from detector


def main():
    init_db()
    if not RAW_PHOTOS_DIR.exists():
        print(f"No raw photos directory found at {RAW_PHOTOS_DIR}. Nothing to retrain.")
        return

    with db_session() as db:
        for user_dir in RAW_PHOTOS_DIR.iterdir():
            if not user_dir.is_dir():
                continue
            employee_id = user_dir.name
            user = db.query(User).filter(User.EmployeeID == employee_id).first()
            if not user:
                print(f"Skipping {employee_id}: no matching user in DB.")
                continue

            # Remove old embeddings for this user before recomputing.
            db.query(FaceEmbedding).filter(FaceEmbedding.UserID == user.UserID).delete()

            count = 0
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
                count += 1
            print(f"{employee_id}: recomputed {count} embeddings.")

    print("Retrain complete.")


if __name__ == "__main__":
    main()
