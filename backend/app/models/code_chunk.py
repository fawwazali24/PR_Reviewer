"""A semantically-chunked piece of repo code with its embedding (RAG index).

Chunks are function/class-level (Tree-sitter-aware), not fixed-size windows.
``content_hash`` lets re-indexing skip embedding regeneration for unchanged
chunks (plan change #6).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.repository import Repository


class CodeChunk(Base):
    __tablename__ = "code_chunks"
    __table_args__ = (
        Index("ix_code_chunks_repo_file", "repository_id", "file_path"),
        Index("ix_code_chunks_repo_hash", "repository_id", "content_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True, nullable=False
    )

    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    symbol_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # function | class | method | module
    chunk_type: Mapped[str] = mapped_column(String(32), nullable=False)

    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Heuristic marker so the retriever can up-weight domain/behavioral context:
    # tests and validation/constraint logic, not just structural neighbors.
    is_test: Mapped[bool] = mapped_column(default=False, nullable=False)

    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim), nullable=False)

    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    repository: Mapped["Repository"] = relationship(back_populates="code_chunks")
