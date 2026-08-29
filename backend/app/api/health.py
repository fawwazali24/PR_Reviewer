"""Health / readiness endpoint.

Verifies the API is up, the database is reachable, and the pgvector extension
is installed — the Phase 0 exit criterion.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db_ok = False
    pgvector_ok = False
    detail: str | None = None
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
        pgvector_ok = bool(
            db.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).first()
        )
    except Exception as exc:  # pragma: no cover - reported, not raised
        detail = str(exc)

    healthy = db_ok and pgvector_ok
    return {
        "status": "ok" if healthy else "degraded",
        "database": db_ok,
        "pgvector": pgvector_ok,
        "detail": detail,
    }
