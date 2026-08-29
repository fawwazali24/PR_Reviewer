"""The verification trace for one finding: what deterministic checks ran, whether
we escalated to a semantic LLM pass, and the final verdict (plan change #3).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import VerificationVerdict
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.review_finding import ReviewFinding


class VerificationResult(Base, TimestampMixin):
    __tablename__ = "verification_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_finding_id: Mapped[int] = mapped_column(
        ForeignKey("review_findings.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    # Deterministic phase (cheap, always runs).
    passed_deterministic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # e.g. {"line_in_diff": true, "file_matches": true,
    #       "symbol_exists": true, "semgrep_contradiction": false}
    deterministic_checks: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Semantic phase (only when escalated); null llm_verified => not escalated.
    escalated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    llm_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    llm_reasoning: Mapped[str | None] = mapped_column(nullable=True)

    final_verdict: Mapped[str] = mapped_column(
        default=VerificationVerdict.UNCERTAIN.value, nullable=False
    )
    adjusted_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    finding: Mapped["ReviewFinding"] = relationship(back_populates="verification")
