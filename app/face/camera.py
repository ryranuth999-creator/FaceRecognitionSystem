"""
Thin wrapper around OpenCV VideoCapture so the same helper is reused
by the API (single-shot capture for /login-face uploads) and the
standalone live-recognition script in training/.
"""
import contextlib
from typing import Iterator

import cv2
import numpy as np


@contextlib.contextmanager
def open_camera(index: int = 0) -> Iterator[cv2.VideoCapture]:
    # Try CAP_DSHOW first on Windows for instant initialization and to avoid ObSensor warnings
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        # Fallback to default backend
        cap = cv2.VideoCapture(index)
        
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera at index {index}")
    try:
        yield cap
    finally:
        cap.release()


def capture_frame(cap: cv2.VideoCapture) -> np.ndarray:
    """Grab a single BGR frame."""
    ok, frame = cap.read()
    if not ok:
        raise RuntimeError("Failed to read frame from camera")
    return frame


def bgr_to_rgb(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
