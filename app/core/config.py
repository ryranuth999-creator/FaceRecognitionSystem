"""
Centralized application configuration.

All values are loaded from environment variables (see .env.example).
Using pydantic-settings gives us validation + type coercion for free.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---------- App ----------
    APP_NAME: str = "FaceRecognitionSystem"
    ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "insecure-dev-key-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ---------- Database ----------
    DB_BACKEND: str = "sqlite"  # "sqlite", "mssql", or "mysql"
    DB_SERVER: str = "localhost"
    DB_PORT: int = 1433
    DB_NAME: str = "FaceRecognitionDB"
    DB_USER: str = "sa"
    DB_PASSWORD: str = ""
    DB_DRIVER: str = "ODBC Driver 17 for SQL Server"
    SQLITE_PATH: str = "./dev.db"

    # ---------- Face recognition ----------
    FACE_MATCH_THRESHOLD: float = 0.45
    FACE_MODEL: str = "hog"  # "hog" (CPU) or "cnn" (GPU)
    UNKNOWN_FACE_DIR: str = "app/static/unknown_faces"
    EMBEDDINGS_PER_USER: int = 20
    ANTISPOOFING_ENABLED: bool = True
    ANTISPOOFING_THRESHOLD: float = 0.35
    ALERT_COOLDOWN_SECONDS: int = 60

    # ---------- Telegram ----------
    TELEGRAM_ENABLED: bool = False
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # ---------- Email ----------
    EMAIL_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    ALERT_EMAIL_RECIPIENTS: str = ""

    # ---------- Camera ----------
    DEFAULT_CAMERA_INDEX: int = 0
    DEFAULT_CAMERA_ID: str = "CAM-01"
    DEFAULT_CAMERA_NAME: str = "Main Entrance"
    CAMERA_API_KEY: str = "camera-secret-api-key"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.DB_BACKEND == "sqlite":
            return f"sqlite:///{self.SQLITE_PATH}"
        elif self.DB_BACKEND == "mysql":
            return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_SERVER}:{self.DB_PORT}/{self.DB_NAME}"
        # SQL Server via pyodbc
        odbc = (
            f"DRIVER={{{self.DB_DRIVER}}};"
            f"SERVER={self.DB_SERVER},{self.DB_PORT};"
            f"DATABASE={self.DB_NAME};"
            f"UID={self.DB_USER};"
            f"PWD={self.DB_PASSWORD};"
            f"TrustServerCertificate=yes;"
        )
        from urllib.parse import quote_plus

        return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}"

    @property
    def alert_recipients_list(self) -> List[str]:
        return [e.strip() for e in self.ALERT_EMAIL_RECIPIENTS.split(",") if e.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
