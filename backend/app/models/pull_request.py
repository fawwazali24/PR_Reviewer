"""A cached pull request summary with locally stored review state."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.repository import Repository
    from app.models.review import Review


class PullRequest(Base, TimestampMixin):
    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repository_id", "number", name="uq_pr_repo_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    number: Mapped[int] = mapped_column(nullable=False)

    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    html_url: Mapped[str] = mapped_column(String(1024), nullable=False)

    head_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    base_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    base_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    changed_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Guard against reviewing the same commit twice (plan change #5).
    last_reviewed_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)

    repository: Mapped["Repository"] = relationship(back_populates="pull_requests")
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="pull_request",
        cascade="all, delete-orphan",
        order_by="desc(Review.created_at)",
    )
