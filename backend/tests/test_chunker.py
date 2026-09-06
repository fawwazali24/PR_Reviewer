"""Tests for Tree-sitter-aware chunking + content hashing (plan Phase 4)."""
from __future__ import annotations

from app.rag.chunker import chunk_file, content_hash, is_test_path

SOURCE = '''\
"""Module docstring."""
import os

CONST = 1


def top_func(x):
    return x + 1


class MyClass:
    def method_a(self):
        return CONST
'''


def test_chunk_file_produces_module_and_symbol_chunks():
    chunks = chunk_file("app/service.py", SOURCE)
    by_type = {}
    for c in chunks:
        by_type.setdefault(c.chunk_type, []).append(c)

    # A module-header chunk (imports/const/docstring) + the two top-level symbols.
    assert "module" in by_type
    names = {c.symbol_name for c in chunks if c.chunk_type != "module"}
    assert names == {"top_func", "MyClass"}

    # Methods are NOT separate top-level chunks; they live inside the class chunk.
    cls_chunk = next(c for c in chunks if c.symbol_name == "MyClass")
    assert "method_a" in cls_chunk.content
    assert cls_chunk.chunk_type == "class"


def test_large_class_is_split_into_class_context_and_method_chunks():
    source = "class Huge:\n" + "\n".join(
        f"    def method_{i}(self):\n        return {i}" for i in range(45)
    )

    chunks = chunk_file("app/large.py", source)

    context = next(c for c in chunks if c.chunk_type == "class_context")
    methods = [c for c in chunks if c.chunk_type == "method"]
    assert context.symbol_name == "Huge"
    assert len(methods) == 45
    assert {c.symbol_name for c in methods} == {
        f"Huge.method_{i}" for i in range(45)
    }
    assert all("def method_" in c.content for c in methods)


def test_module_chunk_holds_the_header_only():
    chunks = chunk_file("app/service.py", SOURCE)
    module_chunk = next(c for c in chunks if c.chunk_type == "module")
    assert module_chunk.start_line == 1
    assert "import os" in module_chunk.content
    assert "def top_func" not in module_chunk.content


def test_is_test_flag_and_path_detection():
    assert is_test_path("tests/test_foo.py") is True
    assert is_test_path("app/foo_test.py") is True
    assert is_test_path("src/testing/helpers.py") is True
    assert is_test_path("app/service.py") is False

    test_chunks = chunk_file("tests/test_service.py", SOURCE)
    assert all(c.is_test for c in test_chunks)
    prod_chunks = chunk_file("app/service.py", SOURCE)
    assert all(not c.is_test for c in prod_chunks)


def test_content_hash_is_stable_and_content_addressed():
    # Same content -> same hash (drives embedding-cache reuse on re-index).
    h1 = content_hash("def f():\n    return 1\n")
    h2 = content_hash("def f():\n    return 1\n")
    h3 = content_hash("def f():\n    return 2\n")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64  # sha256 hex


def test_empty_source_yields_no_chunks():
    assert chunk_file("app/empty.py", "") == []


def test_unparseable_source_falls_back_to_whole_file():
    # Even syntactically-broken Python should index as one module chunk, not vanish.
    broken = "def (((:\n    this is not python\n"
    chunks = chunk_file("app/broken.py", broken)
    assert len(chunks) >= 1
    assert chunks[0].content
