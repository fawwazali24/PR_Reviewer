"""Developer feedback on a surfaced finding (thumbs up/down / false positive).

Captured from the dashboard; the raw material for later precision tuning.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.review_finding import ReviewFinding


class DeveloperFeedback(Base, TimestampMixin):
    __tablename__ = "developer_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_finding_id: Mapped[int] = mapped_column(
        ForeignKey("review_findings.id", ondelete="CASCADE"), index=True, nullable=False
    )

    verdict: Mapped[str] = mapped_column(String(32), nullable=False)  # FeedbackVerdict
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(255), nullable=True)

    finding: Mapped["ReviewFinding"] = relationship(back_populates="feedback")
