import json
import base64
import hashlib
from datetime import datetime
from typing import List

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from cryptography.fernet import Fernet

from app.core.database import Base
from app.core.config import settings


def _get_fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


class FaceEmbedding(Base):
    """
    Stores one face embedding vector per row. A user typically has
    10-30 embeddings captured during registration (different angles /
    lighting) to make recognition more robust.

    The vector is persisted as an AES-encrypted JSON-encoded array inside a
    VARBINARY/LargeBinary column so it is fully secure on SQL Server
    and SQLite.
    """

    __tablename__ = "face_embeddings"

    EmbeddingID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    UserID: Mapped[int] = mapped_column(ForeignKey("users.UserID", ondelete="CASCADE"))
    EmbeddingVector: Mapped[bytes] = mapped_column(LargeBinary)
    Model: Mapped[str] = mapped_column(String(50), default="insightface_buffalo_l_512d")
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="embeddings")

    @staticmethod
    def encode_vector(vector: List[float]) -> bytes:
        raw_data = json.dumps(vector).encode("utf-8")
        fernet = _get_fernet()
        return fernet.encrypt(raw_data)

    @staticmethod
    def decode_vector(blob: bytes) -> List[float]:
        fernet = _get_fernet()
        try:
            decrypted = fernet.decrypt(blob)
            return json.loads(decrypted.decode("utf-8"))
        except Exception:
            # Fallback in case of unencrypted data (e.g. migration / seeding)
            try:
                return json.loads(blob.decode("utf-8"))
            except Exception:
                return []
