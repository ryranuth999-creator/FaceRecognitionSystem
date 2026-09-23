"""
Face detection wrapper.

Uses the `face_recognition` library (built on dlib's HOG or CNN
detectors). This keeps the project runnable on a CPU-only laptop,
matching the assignment's "Webcam/Laptop camera" scenario.

If the `face_recognition` library is not installed (e.g. because compiling
dlib is not supported on this environment), this module automatically
falls back to OpenCV Haar Cascade classifier for face detection and
gray-resized L2-normalized 128-d vectors for face embeddings.
"""
import logging
from typing import List, Tuple, Optional, Any

import cv2
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

BoundingBox = Tuple[int, int, int, int]  # (top, right, bottom, left)

# Attempt to load insightface
insightface_app = None
try:
    import insightface
    from insightface.app import FaceAnalysis
    HAS_INSIGHTFACE = True
    insightface_app = FaceAnalysis(name='buffalo_l', allowed_modules=['detection', 'recognition'])
    # Use CPU with 320x320 detection size for real-time speed on CPU
    insightface_app.prepare(ctx_id=-1, det_size=(320, 320))
except (ImportError, ModuleNotFoundError, Exception):
    logger.warning("InsightFace is not installed. Falling back to dlib/OpenCV Custom 512-D embedding pipeline.")
    HAS_INSIGHTFACE = False

# Attempt to load face_recognition
face_cascade = None
try:
    import face_recognition  # type: ignore
    HAS_FACE_RECOGNITION = True
except (ImportError, ModuleNotFoundError):
    if not HAS_INSIGHTFACE:
        logger.warning(
            "face_recognition package (or dlib) is not installed. "
            "Falling back to OpenCV Haar Cascade classifier for face detection "
            "and custom gray-resized L2-normalized 512-d vectors for face embeddings."
        )
    HAS_FACE_RECOGNITION = False
    
    # Initialize OpenCV Haar Cascade
    import os
    _local_cascade = os.path.join(os.path.dirname(__file__), 'haarcascade_frontalface_default.xml')
    _sys_cascade = os.path.join(cv2.data.haarcascades or '', 'haarcascade_frontalface_default.xml')  # type: ignore
    
    _cascade_path = _local_cascade if os.path.exists(_local_cascade) else _sys_cascade
    face_cascade = cv2.CascadeClassifier(_cascade_path)
    if face_cascade.empty():
        logger.error(f"Failed to load Haar Cascade from {_cascade_path}")


# Define current active model name based on imports
if HAS_INSIGHTFACE:
    ACTIVE_MODEL_NAME = "insightface_buffalo_l_512d"
elif HAS_FACE_RECOGNITION:
    ACTIVE_MODEL_NAME = "face_recognition_v1_128d"
else:
    ACTIVE_MODEL_NAME = "grayscale_fallback_512d"



_last_image_id = None
_last_faces = None


def _get_faces(rgb_image: np.ndarray) -> List[Any]:
    global _last_image_id, _last_faces
    if not HAS_INSIGHTFACE or insightface_app is None:
        return []
        
    img_id = id(rgb_image)
    if _last_image_id == img_id and _last_faces is not None:
        return _last_faces
    
    faces = insightface_app.get(rgb_image)
    _last_image_id = img_id
    _last_faces = faces
    return faces


def detect_faces(rgb_image: np.ndarray) -> List[BoundingBox]:
    """Return bounding boxes for every face found in an RGB image."""
    if HAS_INSIGHTFACE:
        try:
            faces = _get_faces(rgb_image)  # type: ignore
            faces = sorted(faces, key=lambda f: (f['bbox'][2] - f['bbox'][0]) * (f['bbox'][3] - f['bbox'][1]), reverse=True)  # type: ignore
            boxes = []
            for face in faces:
                x1, y1, x2, y2 = face['bbox']
                boxes.append((int(y1), int(x2), int(y2), int(x1)))
            return boxes
        except Exception as e:
            logger.error(f"InsightFace detection failed: {e}. Trying fallback...")
            
    if HAS_FACE_RECOGNITION:
        return face_recognition.face_locations(rgb_image, model=settings.FACE_MODEL)
    
    # Fallback using OpenCV Haar Cascade
    if face_cascade is None:
        return []
    gray = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)
    faces: np.ndarray = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(40, 40))  # type: ignore
    
    boxes = []
    for face in faces:
        x = int(face[0])
        y = int(face[1])
        w = int(face[2])
        h = int(face[3])
        boxes.append((y, x + w, y + h, x))
    return boxes


def get_embeddings(rgb_image: np.ndarray, boxes: Optional[List[BoundingBox]] = None) -> List[np.ndarray]:
    """Return a 512-d embedding vector for each detected face.

    If `boxes` is not supplied, faces are detected first.
    """
    if HAS_INSIGHTFACE:
        try:
            faces = _get_faces(rgb_image)  # type: ignore
            faces = sorted(faces, key=lambda f: (f['bbox'][2] - f['bbox'][0]) * (f['bbox'][3] - f['bbox'][1]), reverse=True)  # type: ignore
            return [face.normed_embedding for face in faces]  # type: ignore
        except Exception as e:
            logger.error(f"InsightFace embedding failed: {e}. Trying fallback...")

    # Fallback: Gray-resized L2-normalized 512-d vector (16x32 grayscale crop)
    if boxes is None:
        boxes = detect_faces(rgb_image)
    if not boxes:
        return []
    
    embeddings = []
    h, w = rgb_image.shape[:2]
    
    for box in boxes:
        top, right, bottom, left = box
        top = max(0, top)
        left = max(0, left)
        bottom = min(h, bottom)
        right = min(w, right)
        
        crop = rgb_image[top:bottom, left:right]
        if crop.size == 0:
            embeddings.append(np.zeros(512))
            continue
            
        # Convert crop to grayscale
        gray_crop = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        
        # Resize to 16x32 (exactly 512 dimensions)
        resized = cv2.resize(gray_crop, (16, 32))
        
        # Flatten
        vector = resized.flatten().astype(float)
        
        # L2 normalize
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
            
        embeddings.append(vector)
        
    return embeddings


def crop_face(bgr_image: np.ndarray, box: BoundingBox, margin: int = 20) -> np.ndarray:
    """Crop a face out of a BGR (OpenCV) image with a small margin, for
    saving evidence snapshots of unknown persons."""
    top, right, bottom, left = box
    h, w = bgr_image.shape[:2]
    top = max(0, top - margin)
    left = max(0, left - margin)
    bottom = min(h, bottom + margin)
    right = min(w, right + margin)
    return bgr_image[top:bottom, left:right]
