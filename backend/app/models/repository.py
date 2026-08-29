"""A GitHub repository registered with the system (source of truth).

With a PAT there is no App-installation event to discover repos from, so this
table IS the registry: repos enter only via the manual URL registration form.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import IndexingStatus
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.code_chunk import CodeChunk
    from app.models.pull_request import PullRequest


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # "owner/name" — unique natural key.
    full_name: Mapped[str] = mapped_column(String(512), unique=True, index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # MVP scope: one language at a time (Python first).
    language: Mapped[str] = mapped_column(String(64), default="python", nullable=False)

    indexing_status: Mapped[str] = mapped_column(
        String(32), default=IndexingStatus.NOT_STARTED.value, nullable=False
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_indexed_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    indexing_error: Mapped[str | None] = mapped_column(String, nullable=True)

    pull_requests: Mapped[list["PullRequest"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    code_chunks: Mapped[list["CodeChunk"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
