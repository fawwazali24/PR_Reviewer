"""A Semgrep finding for a review.

Used inside the pipeline as *corroborating* signal for LLM findings — never
surfaced to the dashboard as a standalone "new" finding, since CI already runs
this class of check (see README).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.review import Review


class StaticAnalysisFinding(Base):
    __tablename__ = "static_analysis_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False
    )

    tool: Mapped[str] = mapped_column(String(64), default="semgrep", nullable=False)
    rule_id: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str | None] = mapped_column(String, nullable=True)

    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    review: Mapped["Review"] = relationship(back_populates="static_findings")
