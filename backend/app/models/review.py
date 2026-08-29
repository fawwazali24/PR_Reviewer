"""A single review run over one PR at one commit sha.

Its lifecycle status (queued -> running -> done/failed) is what the dashboard
polls; that polling is a cheap DB read, never a re-run of the pipeline.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import ReviewStatus
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.changed_file import ChangedFile
    from app.models.pull_request import PullRequest
    from app.models.review_finding import ReviewFinding
    from app.models.static_analysis_finding import StaticAnalysisFinding


class Review(Base, TimestampMixin):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # The exact commit reviewed (copied into Pr.last_reviewed_sha on success).
    head_sha: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), default=ReviewStatus.QUEUED.value, nullable=False, index=True
    )
    # Short human-facing note on the current step, e.g. "running semgrep".
    stage: Mapped[str | None] = mapped_column(String(128), nullable=True)

    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    # Denormalized count of verified findings, for cheap list rendering.
    finding_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    pull_request: Mapped["PullRequest"] = relationship(back_populates="reviews")
    changed_files: Mapped[list["ChangedFile"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )
    findings: Mapped[list["ReviewFinding"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )
    static_findings: Mapped[list["StaticAnalysisFinding"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )
