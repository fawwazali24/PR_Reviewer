"""An LLM-produced review finding — the primary output of the system.

Fields mirror the spec's finding JSON exactly (file, start_line, end_line,
severity, category, title, description, evidence, suggested_fix, confidence)
plus a verification verdict, a GitHub deep-link, and the confidence after any
adjustment by the verification layer.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import VerificationVerdict
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.developer_feedback import DeveloperFeedback
    from app.models.review import Review
    from app.models.verification_result import VerificationResult


class ReviewFinding(Base, TimestampMixin):
    __tablename__ = "review_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # ---- spec finding JSON ----
    file: Mapped[str] = mapped_column(String(1024), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    evidence: Mapped[str | None] = mapped_column(String, nullable=True)
    suggested_fix: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # ---- verification-layer outputs ----
    verdict: Mapped[str] = mapped_column(
        String(32), default=VerificationVerdict.UNCERTAIN.value, nullable=False
    )
    adjusted_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # False for findings that failed verification / fell below threshold; the
    # dashboard shows only surfaced findings, but we keep the rest for evals.
    surfaced: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Deep link: github.com/owner/repo/blob/{sha}/{path}#L{start}-L{end}
    github_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    review: Mapped["Review"] = relationship(back_populates="findings")
    verification: Mapped["VerificationResult | None"] = relationship(
        back_populates="finding", cascade="all, delete-orphan", uselist=False
    )
    feedback: Mapped[list["DeveloperFeedback"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )
