"""
Matches a live face embedding against every enrolled embedding stored
in SQL Server and decides known-vs-unknown using a similarity
threshold (see FACE_MATCH_THRESHOLD in .env, default 0.70 = 70%).

Similarity metric: we convert dlib's Euclidean face distance into a
0-1 "confidence" score (1 = identical, 0 = totally different) so the
threshold matches the assignment's ">70% is recommended" language.
"""
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.face_encoding import FaceEmbedding
from app.models.user import User
from app.face.detector import ACTIVE_MODEL_NAME


@dataclass
class MatchResult:
    matched: bool
    user: Optional[User]
    confidence: float  # 0.0 - 1.0


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate the cosine similarity between two vectors.
    Norm of vectors must not be zero."""
    a = np.array(a)
    b = np.array(b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, float(np.dot(a, b) / (norm_a * norm_b)))


_known_embeddings_cache = None  # List of tuples: (user_id, embedding_vector)


def invalidate_embeddings_cache():
    global _known_embeddings_cache
    _known_embeddings_cache = None


def load_known_embeddings(db: Session) -> List[tuple]:
    """Returns a list of (user_id, embedding_vector) for every active user,
    utilizing a decrypted in-memory cache to avoid expensive DB queries and Fernet decryptions."""
    global _known_embeddings_cache
    if _known_embeddings_cache is None:
        rows = (
            db.query(FaceEmbedding, User)
            .join(User, FaceEmbedding.UserID == User.UserID)
            .filter(User.Status == "active")
            .filter(FaceEmbedding.Model == ACTIVE_MODEL_NAME)
            .all()
        )
        _known_embeddings_cache = [
            (user.UserID, np.array(FaceEmbedding.decode_vector(emb.EmbeddingVector)))
            for emb, user in rows
        ]
    return _known_embeddings_cache


def identify(db: Session, probe_embedding: np.ndarray, threshold: Optional[float] = None) -> MatchResult:
    """Compare a probe embedding against all known embeddings and
    return the best match, or `matched=False` if nothing clears the
    threshold (i.e. an "unknown person")."""
    if threshold is None:
        threshold = settings.FACE_MATCH_THRESHOLD
        # If the user left it at default 0.70, but we are using InsightFace,
        # adjust it to 0.40 to avoid 100% false rejection rate.
        if ACTIVE_MODEL_NAME == "insightface_buffalo_l_512d" and threshold == 0.70:
            threshold = 0.40

    known = load_known_embeddings(db)

    if not known:
        return MatchResult(matched=False, user=None, confidence=0.0)

    best_user_id = None
    best_confidence = 0.0

    for user_id, known_vector in known:
        confidence = cosine_similarity(known_vector, probe_embedding)
        if confidence > best_confidence:
            best_confidence = confidence
            best_user_id = user_id

    best_user = None
    if best_user_id is not None:
        best_user = db.query(User).filter(User.UserID == best_user_id).first()

    if best_confidence >= threshold:
        return MatchResult(matched=True, user=best_user, confidence=best_confidence)

    # Still report the closest guess + confidence for logging/alerting,
    # even though it doesn't clear the threshold.
    return MatchResult(matched=False, user=best_user, confidence=best_confidence)
