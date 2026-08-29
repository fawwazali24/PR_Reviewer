"""A file touched by the PR, with its diff hunk and parsed line ranges."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.review import Review


class ChangedFile(Base):
    __tablename__ = "changed_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False
    )

    filename: Mapped[str] = mapped_column(String(1024), nullable=False)
    previous_filename: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # added/modified/removed/renamed
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)

    additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Raw unified-diff patch for this file (as returned by GitHub).
    patch: Mapped[str | None] = mapped_column(String, nullable=True)

    # Parsed added-line ranges on the head commit: [[start, end], ...].
    # This is the load-bearing line mapping findings/deep-links anchor to.
    added_line_ranges: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    review: Mapped["Review"] = relationship(back_populates="changed_files")
