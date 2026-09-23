"""
SQLAlchemy engine / session management.

Works against SQL Server (production) or SQLite (local dev, set
DB_BACKEND=sqlite in .env) without changing any application code.
"""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.DB_BACKEND == "sqlite" else {}

engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    connect_args=connect_args,
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session():
    """Context manager for use outside of FastAPI request handlers
    (e.g. in the standalone camera / training scripts)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Create all tables. In production prefer Alembic migrations;
    this is convenient for first-run / demo purposes."""
    from app.models import user, face_encoding, log  # noqa: F401  (register models)

    Base.metadata.create_all(bind=engine)
