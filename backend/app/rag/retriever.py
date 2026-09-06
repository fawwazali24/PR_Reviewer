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

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.rag.embeddings import embed_texts
from app.models import CodeChunk
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
_RRF_K = 60
_SEMANTIC_WEIGHT = 1.0
_BM25_WEIGHT = 0.3
_BM25_K1 = 1.5
_BM25_B = 0.75
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")


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


def _tokenize(text: str) -> list[str]:
    """Tokenize code while retaining identifiers useful for lexical matching."""
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(text):
        normalized = token.lower()
        tokens.append(normalized)
        if "_" in normalized:
            tokens.extend(part for part in normalized.split("_") if part)
    return tokens


def _bm25_scores(
    chunks: list[CodeChunk], query: str
) -> list[tuple[CodeChunk, float]]:
    """Score chunks lexically with BM25 and return positive-scoring matches."""
    query_terms = set(_tokenize(query))
    if not query_terms or not chunks:
        return []

    documents = [_tokenize(chunk.content) for chunk in chunks]
    document_frequency: dict[str, int] = {}
    for document in documents:
        for term in set(document):
            document_frequency[term] = document_frequency.get(term, 0) + 1

    average_length = sum(len(document) for document in documents) / len(documents)
    total_documents = len(documents)
    scored: list[tuple[CodeChunk, float]] = []
    for chunk, document in zip(chunks, documents):
        if not document:
            continue
        term_frequency = {term: document.count(term) for term in query_terms}
        length_ratio = len(document) / average_length if average_length else 1.0
        score = 0.0
        for term, frequency in term_frequency.items():
            if not frequency:
                continue
            df = document_frequency.get(term, 0)
            idf = max(0.0, (total_documents - df + 0.5) / (df + 0.5))
            numerator = frequency * (_BM25_K1 + 1)
            denominator = frequency + _BM25_K1 * (1 - _BM25_B + _BM25_B * length_ratio)
            score += idf * numerator / denominator
        if score > 0:
            scored.append((chunk, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def _rrf_score(rank: int) -> float:
    return 1.0 / (_RRF_K + rank)


def retrieve_context(
    db: Session,
    repository_id: int,
    query_texts: list[str],
    *,
    k: int | None = None,
    exclude_files: set[str] | None = None,
) -> list[RetrievedChunk]:
    """Fuse semantic and BM25 retrieval, then rerank toward domain context."""
    k = k or settings.retrieval_top_k
    queries = [q for q in query_texts if q.strip()]
    if not queries:
        return []

    # Over-fetch per query so hybrid fusion and domain reranking have candidates
    # to promote before the final top-k slice.
    per_query = max(k, 5)

    query_vecs = embed_texts(queries)
    semantic_best: dict[int, tuple[CodeChunk, float]] = {}
    for vec in query_vecs:
        for chunk, dist in search(db, repository_id, vec, per_query, exclude_files):
            prev = semantic_best.get(chunk.id)
            if prev is None or dist < prev[1]:
                semantic_best[chunk.id] = (chunk, dist)

    stmt = select(CodeChunk).where(CodeChunk.repository_id == repository_id)
    if exclude_files:
        stmt = stmt.where(CodeChunk.file_path.notin_(exclude_files))
    corpus = list(db.scalars(stmt))

    bm25_best: dict[int, tuple[CodeChunk, float]] = {}
    for query in queries:
        for chunk, score in _bm25_scores(corpus, query)[:per_query]:
            prev = bm25_best.get(chunk.id)
            if prev is None or score > prev[1]:
                bm25_best[chunk.id] = (chunk, score)

    semantic_ranked = sorted(semantic_best.values(), key=lambda item: item[1])
    bm25_ranked = sorted(bm25_best.values(), key=lambda item: item[1], reverse=True)
    fused: dict[int, tuple[CodeChunk, float, float | None]] = {}
    for rank, (chunk, distance) in enumerate(semantic_ranked, start=1):
        fused[chunk.id] = (chunk, _SEMANTIC_WEIGHT * _rrf_score(rank), distance)
    for rank, (chunk, _score) in enumerate(bm25_ranked, start=1):
        previous = fused.get(chunk.id)
        if previous is None:
            fused[chunk.id] = (chunk, _BM25_WEIGHT * _rrf_score(rank), None)
        else:
            fused[chunk.id] = (
                chunk,
                previous[1] + _BM25_WEIGHT * _rrf_score(rank),
                previous[2],
            )

    ranked: list[RetrievedChunk] = []
    for chunk, fusion_score, _semantic_distance in fused.values():
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
                # Keep lower-is-better semantics for the public result while
                # using the hybrid score for ranking.
                distance=(1.0 / fusion_score) * weight,
            )
        )

    ranked.sort(key=lambda c: c.distance)
    return ranked[:k]
