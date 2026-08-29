"""pgvector read/write for code chunks.

Re-indexing is content-hash based (plan change #6): an unchanged chunk reuses
its existing embedding instead of paying to regenerate it. A full re-index
replaces the repo's chunk set but carries embeddings forward by content hash.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import CodeChunk
from app.rag.chunker import ChunkData
from app.rag.embeddings import embed_texts

logger = logging.getLogger(__name__)


@dataclass
class IndexStats:
    total: int = 0
    reused: int = 0   # embeddings carried forward by content hash
    embedded: int = 0  # embeddings freshly computed


def upsert_repository_chunks(
    db: Session, repository_id: int, chunks: list[ChunkData]
) -> IndexStats:
    """Replace the repo's chunk set, reusing embeddings for unchanged content."""
    stats = IndexStats(total=len(chunks))

    # Carry embeddings forward for any content we've already embedded.
    existing: dict[str, list[float]] = {}
    for row in db.scalars(
        select(CodeChunk).where(CodeChunk.repository_id == repository_id)
    ):
        existing.setdefault(row.content_hash, row.embedding)

    to_embed_idx = [i for i, c in enumerate(chunks) if c.content_hash not in existing]
    stats.reused = len(chunks) - len(to_embed_idx)

    fresh: list[list[float]] = []
    if to_embed_idx:
        fresh = embed_texts([chunks[i].content for i in to_embed_idx])
        stats.embedded = len(fresh)
    fresh_by_idx = dict(zip(to_embed_idx, fresh))

    # Swap out the old chunk set for the new one.
    db.execute(delete(CodeChunk).where(CodeChunk.repository_id == repository_id))
    db.flush()

    for i, c in enumerate(chunks):
        embedding = fresh_by_idx.get(i) or existing.get(c.content_hash)
        db.add(
            CodeChunk(
                repository_id=repository_id,
                file_path=c.file_path,
                symbol_name=c.symbol_name,
                chunk_type=c.chunk_type,
                start_line=c.start_line,
                end_line=c.end_line,
                content=c.content,
                content_hash=c.content_hash,
                is_test=c.is_test,
                embedding=embedding,
            )
        )
    db.flush()
    logger.info(
        "indexed repo %s: %s chunks (%s reused, %s embedded)",
        repository_id, stats.total, stats.reused, stats.embedded,
    )
    return stats


def search(
    db: Session,
    repository_id: int,
    embedding: list[float],
    k: int,
    exclude_files: set[str] | None = None,
) -> list[tuple[CodeChunk, float]]:
    """Top-k chunks by cosine distance, optionally excluding some files."""
    distance = CodeChunk.embedding.cosine_distance(embedding).label("distance")
    stmt = select(CodeChunk, distance).where(CodeChunk.repository_id == repository_id)
    if exclude_files:
        stmt = stmt.where(CodeChunk.file_path.notin_(exclude_files))
    stmt = stmt.order_by(distance).limit(k)
    return [(row[0], float(row[1])) for row in db.execute(stmt).all()]
