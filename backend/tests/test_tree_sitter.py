"""Tests for Tree-sitter symbol extraction (plan Phase 3)."""
from __future__ import annotations

from app.analysis.tree_sitter import (
    all_identifiers,
    defined_names,
    enclosing_symbols,
    parse_symbols,
    top_level_symbols,
)

SOURCE = '''\
import os

CONST = 1


def top_func(x):
    return x + 1


class MyClass:
    def method_a(self):
        return CONST

    def method_b(self):
        return top_func(1)
'''


def _by_name(symbols):
    return {s.name: s for s in symbols}


def test_parse_symbols_finds_functions_classes_methods():
    syms = _by_name(parse_symbols(SOURCE))
    assert set(syms) == {"top_func", "MyClass", "method_a", "method_b"}

    assert syms["top_func"].kind == "function"
    assert syms["top_func"].parent is None

    assert syms["MyClass"].kind == "class"

    # Methods carry their enclosing class as parent + qualified_name.
    assert syms["method_a"].kind == "method"
    assert syms["method_a"].parent == "MyClass"
    assert syms["method_a"].qualified_name == "MyClass.method_a"
    assert syms["method_b"].parent == "MyClass"


def test_symbol_line_spans_are_1_indexed_inclusive():
    syms = _by_name(parse_symbols(SOURCE))
    # `def top_func` is on line 6 of SOURCE.
    assert syms["top_func"].start_line == 6
    assert syms["top_func"].end_line == 7
    # `class MyClass` starts at line 11 and runs to the last line.
    assert syms["MyClass"].start_line == 11


def test_top_level_symbols_excludes_methods():
    names = {s.name for s in top_level_symbols(SOURCE)}
    assert names == {"top_func", "MyClass"}


def test_enclosing_symbols_for_changed_range():
    # method_b's body is around lines 15-16.
    enclosing = {s.qualified_name for s in enclosing_symbols(SOURCE, [(16, 16)])}
    # The change is inside MyClass -> method_b, so both should enclose it.
    assert "MyClass.method_b" in enclosing
    assert "MyClass" in enclosing
    assert "top_func" not in enclosing


def test_enclosing_symbols_empty_when_no_ranges():
    assert enclosing_symbols(SOURCE, []) == []


def test_defined_names_and_all_identifiers():
    assert defined_names(SOURCE) == {"top_func", "MyClass", "method_a", "method_b"}

    idents = all_identifiers(SOURCE)
    for expected in ("os", "CONST", "top_func", "x", "MyClass", "method_a", "self"):
        assert expected in idents
