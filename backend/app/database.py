"""Database engine, session factory, and FastAPI dependency.

Sync SQLAlchemy on purpose: the pipeline's heavy steps (tree-sitter, semgrep
subprocess, sentence-transformers) are all blocking/CPU-bound, so an async DB
buys nothing and complicates the code. FastAPI runs ``def`` endpoints and
``BackgroundTasks`` in a threadpool, which is exactly what we want here.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,   # recycle dead connections (matters with docker restarts)
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Standalone transactional session for background tasks / scripts.

    Commits on success, rolls back on error, always closes.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
