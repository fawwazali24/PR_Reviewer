"""Tests for hybrid semantic and BM25 retrieval."""
from __future__ import annotations

from types import SimpleNamespace

from app.rag import retriever


def _chunk(chunk_id: int, content: str, *, is_test: bool = False):
    return SimpleNamespace(
        id=chunk_id,
        content=content,
        file_path=f"file_{chunk_id}.py",
        symbol_name=None,
        chunk_type="function",
        start_line=1,
        end_line=2,
        is_test=is_test,
    )


def test_bm25_prefers_lexical_matches():
    chunks = [
        _chunk(1, "def unrelated():\n    return 1"),
        _chunk(2, "def validate_permission(user):\n    return user.is_admin"),
    ]

    matches = retriever._bm25_scores(chunks, "validate permission")

    assert matches[0][0].id == 2
    assert matches[0][1] > 0


def test_retriever_unions_semantic_and_bm25_results(monkeypatch):
    semantic_chunk = _chunk(1, "def unrelated():\n    return 1")
    lexical_chunk = _chunk(2, "def validate_permission(user):\n    return user.is_admin")
    corpus = [semantic_chunk, lexical_chunk]

    class FakeDb:
        def scalars(self, _statement):
            return corpus

    monkeypatch.setattr(retriever, "embed_texts", lambda _queries: [[0.0]])
    monkeypatch.setattr(
        retriever,
        "search",
        lambda *_args: [(semantic_chunk, 0.1)],
    )

    results = retriever.retrieve_context(
        FakeDb(),
        repository_id=1,
        query_texts=["validate permission"],
        k=2,
    )

    assert {chunk.file_path for chunk in results} == {"file_1.py", "file_2.py"}