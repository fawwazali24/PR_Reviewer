"""Pytest bootstrap.

Runs before any app module is imported, so environment defaults set here are
picked up by the lru_cached settings. Keeps the pure-logic tests independent of
whatever a local ``.env`` might contain.
"""
from __future__ import annotations

import os

# Deterministic threshold for the confidence-gate tests.
os.environ.setdefault("CONFIDENCE_THRESHOLD", "0.55")
# Never touch a real database during unit tests (create_engine is lazy anyway).
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
