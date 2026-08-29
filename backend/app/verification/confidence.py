"""Confidence threshold filter.

Decides which verified findings actually reach the dashboard. The threshold is
a single knob (``CONFIDENCE_THRESHOLD``) meant to be tuned against the eval
fixture set (plan change #8), trading recall for the precision the spec asks for.
"""
from __future__ import annotations

from app.config import settings
from app.enums import VerificationVerdict


def should_surface(final_verdict: str, adjusted_confidence: float) -> bool:
    """A finding is shown only if it wasn't rejected and clears the threshold."""
    if final_verdict == VerificationVerdict.REJECTED.value:
        return False
    return adjusted_confidence >= settings.confidence_threshold
