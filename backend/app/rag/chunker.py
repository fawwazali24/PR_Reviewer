"""Tree-sitter-aware chunking.

Chunks are function/class-level, not fixed-size windows, so each chunk is a
semantically whole unit the embedder can represent well. Top-level code
(imports, constants, module docstring) becomes a single "module" chunk.
Falls back to a whole-file chunk if the file can't be parsed.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.analysis.tree_sitter import class_method_symbols, top_level_symbols

_TEST_PATH_RE = re.compile(r"(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.py$|_test\.py$", re.IGNORECASE)
_LARGE_CLASS_LINES = 80


@dataclass
class ChunkData:
    file_path: str
    symbol_name: str | None
    chunk_type: str          # function | class | class_context | method | module
    start_line: int
    end_line: int
    content: str
    is_test: bool
    content_hash: str


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_test_path(path: str) -> bool:
    return bool(_TEST_PATH_RE.search(path))


def _slice(lines: list[str], start: int, end: int) -> str:
    """1-indexed inclusive slice."""
    return "\n".join(lines[start - 1 : end])


def chunk_file(file_path: str, source: str) -> list[ChunkData]:
    """Split one Python source file into semantic chunks."""
    is_test = is_test_path(file_path)
    lines = source.splitlines()
    if not lines:
        return []

    def make(symbol: str | None, kind: str, start: int, end: int) -> ChunkData:
        body = _slice(lines, start, end)
        return ChunkData(
            file_path=file_path,
            symbol_name=symbol,
            chunk_type=kind,
            start_line=start,
            end_line=end,
            content=body,
            is_test=is_test,
            content_hash=content_hash(body),
        )

    try:
        symbols = top_level_symbols(source)
    except Exception:
        # Parse failure: index the whole file as one chunk rather than nothing.
        return [make(None, "module", 1, len(lines))]

    chunks: list[ChunkData] = []

    # Module-header chunk: everything above the first top-level symbol.
    first_start = min((s.start_line for s in symbols), default=len(lines) + 1)
    header_end = first_start - 1
    if header_end >= 1 and _slice(lines, 1, header_end).strip():
        chunks.append(make(None, "module", 1, header_end))

    for sym in symbols:
        if sym.kind == "class" and sym.end_line - sym.start_line + 1 > _LARGE_CLASS_LINES:
            methods = class_method_symbols(source, sym.name)
            if methods:
                first_method_start = min(method.start_line for method in methods)
                context_end = first_method_start - 1
                if _slice(lines, sym.start_line, context_end).strip():
                    chunks.append(
                        make(sym.name, "class_context", sym.start_line, context_end)
                    )
                for method in methods:
                    chunks.append(
                        make(
                            method.qualified_name,
                            "method",
                            method.start_line,
                            method.end_line,
                        )
                    )
                continue
        chunks.append(make(sym.name, sym.kind, sym.start_line, sym.end_line))

    if not chunks:  # file had only whitespace between symbols, etc.
        chunks.append(make(None, "module", 1, len(lines)))
    return chunks
