"""Retrieval, weighted toward domain/business context.

Plain nearest-neighbor retrieval surfaces syntactic look-alikes. For judging
business-logic consistency we specifically want the *other* places a rule is
enforced, the tests that encode expected behavior, and validation/constraint
logic — so we up-weight test and validation chunks after the raw similarity
search. This is what lets the LLM reason about intent, not just structure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import settings
from app.rag.embeddings import embed_texts
from app.rag.vector_store import search

# Symbol-name signals that a chunk encodes a rule/constraint/authorization.
_VALIDATION_RE = re.compile(
    r"valid|verif|check|ensure|assert|constraint|rule|permission|authori[sz]|"
    r"guard|require|allow|forbid|limit|policy|invariant|sanitiz",
    re.IGNORECASE,
)

# Multiplicative weights on cosine distance (lower = ranked higher).
_TEST_WEIGHT = 0.82
_VALIDATION_WEIGHT = 0.82


@dataclass
class RetrievedChunk:
    file_path: str
    symbol_name: str | None
    chunk_type: str
    start_line: int
    end_line: int
    content: str
    is_test: bool
    is_validation: bool
    distance: float


def _is_validation(symbol_name: str | None) -> bool:
    return bool(symbol_name and _VALIDATION_RE.search(symbol_name))


def retrieve_context(
    db: Session,
    repository_id: int,
    query_texts: list[str],
    *,
    k: int | None = None,
    exclude_files: set[str] | None = None,
) -> list[RetrievedChunk]:
    """Embed each query, union nearest neighbors, re-rank toward domain context."""
    k = k or settings.retrieval_top_k
    queries = [q for q in query_texts if q.strip()]
    if not queries:
        return []

    query_vecs = embed_texts(queries)
    # Over-fetch per query so the domain re-rank has candidates to promote.
    per_query = max(k, 5)

    best: dict[int, tuple] = {}  # chunk.id -> (chunk, distance)
    for vec in query_vecs:
        for chunk, dist in search(db, repository_id, vec, per_query, exclude_files):
            prev = best.get(chunk.id)
            if prev is None or dist < prev[1]:
                best[chunk.id] = (chunk, dist)

    ranked: list[RetrievedChunk] = []
    for chunk, dist in best.values():
        is_val = _is_validation(chunk.symbol_name)
        weight = 1.0
        if chunk.is_test:
            weight *= _TEST_WEIGHT
        if is_val:
            weight *= _VALIDATION_WEIGHT
        ranked.append(
            RetrievedChunk(
                file_path=chunk.file_path,
                symbol_name=chunk.symbol_name,
                chunk_type=chunk.chunk_type,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                content=chunk.content,
                is_test=chunk.is_test,
                is_validation=is_val,
                distance=dist * weight,
            )
        )

    ranked.sort(key=lambda c: c.distance)
    return ranked[:k]
