"""Tests for Tree-sitter symbol extraction (plan Phase 3)."""
from __future__ import annotations

from app.analysis.tree_sitter import (
    all_identifiers,
    class_method_symbols,
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


DECORATED_SOURCE = '''\
def decorator(fn):
    return fn

@decorator
def decorated_function():
    pass

@decorator
class DecoratedClass:
    @decorator
    def decorated_method(self):
        pass
'''


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
    # `class MyClass` starts at line 10 and runs to the last line.
    assert syms["MyClass"].start_line == 10


def test_top_level_symbols_excludes_methods():
    names = {s.name for s in top_level_symbols(SOURCE)}
    assert names == {"top_func", "MyClass"}


def test_decorated_definitions_use_nested_name_and_outer_start_line():
    parsed = _by_name(parse_symbols(DECORATED_SOURCE))
    top_level = _by_name(top_level_symbols(DECORATED_SOURCE))
    methods = class_method_symbols(DECORATED_SOURCE, "DecoratedClass")

    assert parsed["decorated_function"].kind == "function"
    assert parsed["decorated_function"].start_line == 4
    assert parsed["DecoratedClass"].start_line == 8
    assert top_level["decorated_function"].start_line == 4
    assert top_level["DecoratedClass"].start_line == 8
    assert len(methods) == 1
    assert methods[0].qualified_name == "DecoratedClass.decorated_method"
    assert methods[0].start_line == 10


def test_enclosing_symbols_for_changed_range():
    # method_b's body is on line 15.
    enclosing = {s.qualified_name for s in enclosing_symbols(SOURCE, [(15, 15)])}
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
