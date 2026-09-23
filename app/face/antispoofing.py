import cv2
import numpy as np
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

def verify_liveness(bgr_frame: np.ndarray, box: Tuple[int, int, int, int]) -> Tuple[bool, float]:
    """
    Performs passive liveness detection on the cropped face image
    to prevent presentation attacks (printed photos, phone/tablet screens).
    
    Uses texture and frequency analysis (Laplacian variance for blur detection,
    and HSV color distribution checks for screen reflection/moire patterns).
    
    Returns:
        (is_live: bool, score: float)
    """
    top, right, bottom, left = box
    h, w = bgr_frame.shape[:2]
    
    # Clip box coordinates
    top = max(0, top)
    left = max(0, left)
    bottom = min(h, bottom)
    right = min(w, right)
    
    face_crop = bgr_frame[top:bottom, left:right]
    if face_crop.size == 0:
        return False, 0.0

    # 1. Texture Analysis (Blurriness Check)
    # Printed photos and screen displays cropped from a webcam frame generally have
    # much lower focus/high-frequency detail than live faces.
    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    # Scale laplacian variance to a liveness score component (0.0 to 1.0)
    # Natural live faces under normal camera focus typically score >100.
    blur_score = min(laplacian_var / 250.0, 1.0)
    
    # 2. Color Distribution / Reflection Check
    # Screen displays have highly saturated color bands (due to emissive LCD/OLED light)
    # compared to natural skin diffuse reflectance.
    hsv = cv2.cvtColor(face_crop, cv2.COLOR_BGR2HSV)
    h_channel, s_channel, v_channel = cv2.split(hsv)
    
    # High standard deviation in value (V) and saturation (S) represents harsh screen glare
    s_std = np.std(s_channel)
    v_std = np.std(v_channel)
    
    # Screens and prints often have uniform reflection profiles or extreme saturation spikes
    reflection_factor = 1.0
    if s_std < 10.0 or v_std < 10.0:  # Very flat lighting, typical of flat paper prints
        reflection_factor = 0.5
    elif s_std > 80.0:  # Excessively high display saturation
        reflection_factor = 0.6
        
    # Calculate final combined liveness score
    liveness_score = float(blur_score * reflection_factor)
    
    # Threshold check (0.35 is recommended for a balanced CPU heuristic)
    is_live = liveness_score >= 0.35
    
    logger.info(f"Liveness Check -> Score: {liveness_score:.3f} (Laplacian: {laplacian_var:.1f}, S-std: {s_std:.1f}), Live={is_live}")
    return is_live, liveness_score
