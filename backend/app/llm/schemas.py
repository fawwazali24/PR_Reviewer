"""Pydantic schemas for LLM I/O.

``LLMFinding`` mirrors the spec's finding JSON exactly. Severity/category are
plain strings here (not Literals) to keep the Gemini structured-output schema
robust; the reviewer normalizes them against the canonical enums afterward.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LLMFinding(BaseModel):
    file: str = Field(description="Repo-relative path of the changed file")
    start_line: int = Field(description="1-indexed start line on the PR head commit")
    end_line: int = Field(description="1-indexed end line (>= start_line)")
    severity: str = Field(description="info | low | medium | high | critical")
    category: str = Field(
        description="business_logic | security | cross_file | maintainability | test_coverage"
    )
    title: str = Field(description="Short reviewer-style headline")
    description: str = Field(
        description="Reviewer's comment, phrased as an open question where apt"
    )
    evidence: str = Field(
        description="Concrete pointer: the diff line, retrieved rule/test, or symbol"
    )
    suggested_fix: str | None = Field(default=None)
    confidence: float = Field(description="0.0-1.0 subjective confidence this is a real issue")


class LLMReviewOutput(BaseModel):
    summary: str = Field(description="1-3 sentence overall take for the reviewer")
    findings: list[LLMFinding] = Field(default_factory=list)


class VerificationDecision(BaseModel):
    """Second-pass semantic verification of a single finding."""

    is_real: bool = Field(description="True if the issue genuinely holds for this PR")
    reasoning: str = Field(description="Brief justification, citing context")
    adjusted_confidence: float = Field(description="0.0-1.0 confidence after review")
