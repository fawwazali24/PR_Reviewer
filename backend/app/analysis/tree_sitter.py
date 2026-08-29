"""Tree-sitter-based Python structural analysis.

Two jobs:
  1. Chunking / context: extract function & class boundaries (with line ranges)
     so we can map changed lines -> enclosing symbols and chunk the repo.
  2. Verification: cheaply answer "does this symbol actually exist in the file?"
     for the deterministic checks in the verification layer.

Python-only for the MVP (plan change #7); add grammars per language later.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

_DEF_TYPES = {"function_definition", "class_definition"}


@dataclass
class Symbol:
    name: str
    kind: str          # function | method | class
    start_line: int    # 1-indexed, inclusive
    end_line: int      # 1-indexed, inclusive
    parent: str | None = None  # enclosing class name for methods

    @property
    def qualified_name(self) -> str:
        return f"{self.parent}.{self.name}" if self.parent else self.name


@lru_cache(maxsize=1)
def _get_parser() -> Any:
    """Lazily build the Python parser (imports the heavy grammar once)."""
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser

    language = Language(tspython.language())
    try:
        return Parser(language)            # tree-sitter >= 0.22 signature
    except TypeError:                      # pragma: no cover - older API fallback
        parser = Parser()
        parser.language = language
        return parser


def _node_text(node: Any, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8", "replace")


def parse_symbols(source: str) -> list[Symbol]:
    """Return every function/class/method definition with its line span."""
    source_bytes = source.encode("utf-8")
    tree = _get_parser().parse(source_bytes)
    symbols: list[Symbol] = []

    def visit(node: Any, class_parent: str | None) -> None:
        for child in node.children:
            if child.type in _DEF_TYPES:
                name_node = child.child_by_field_name("name")
                name = _node_text(name_node, source_bytes) if name_node else "<anonymous>"
                if child.type == "class_definition":
                    kind = "class"
                    symbols.append(
                        Symbol(name, kind, child.start_point[0] + 1,
                               child.end_point[0] + 1, class_parent)
                    )
                    # Recurse into the class body so methods get parent=name.
                    body = child.child_by_field_name("body")
                    if body is not None:
                        visit(body, name)
                else:
                    kind = "method" if class_parent else "function"
                    symbols.append(
                        Symbol(name, kind, child.start_point[0] + 1,
                               child.end_point[0] + 1, class_parent)
                    )
                    body = child.child_by_field_name("body")
                    if body is not None:
                        visit(body, class_parent)
            else:
                visit(child, class_parent)

    visit(tree.root_node, None)
    return symbols


def top_level_symbols(source: str) -> list[Symbol]:
    """Top-level functions + classes only — the unit of RAG chunking."""
    source_bytes = source.encode("utf-8")
    tree = _get_parser().parse(source_bytes)
    out: list[Symbol] = []
    for child in tree.root_node.children:
        if child.type in _DEF_TYPES:
            name_node = child.child_by_field_name("name")
            name = _node_text(name_node, source_bytes) if name_node else "<anonymous>"
            kind = "class" if child.type == "class_definition" else "function"
            out.append(Symbol(name, kind, child.start_point[0] + 1, child.end_point[0] + 1))
    return out


def enclosing_symbols(source: str, changed_ranges: list[tuple[int, int]]) -> list[Symbol]:
    """Symbols whose span intersects any changed line range."""
    if not changed_ranges:
        return []
    result: list[Symbol] = []
    for sym in parse_symbols(source):
        if any(
            not (sym.end_line < s or sym.start_line > e) for s, e in changed_ranges
        ):
            result.append(sym)
    return result


def defined_names(source: str) -> set[str]:
    """Names of every function/class/method defined in the file."""
    return {s.name for s in parse_symbols(source)}


def all_identifiers(source: str) -> set[str]:
    """Every identifier token in the file (used by verification's symbol check)."""
    source_bytes = source.encode("utf-8")
    tree = _get_parser().parse(source_bytes)
    names: set[str] = set()

    def visit(node: Any) -> None:
        if node.type == "identifier":
            names.add(_node_text(node, source_bytes))
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return names
