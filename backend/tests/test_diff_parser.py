"""Tests for the diff parser — the load-bearing line-mapping (plan Phase 3).

The whole verification pipeline hangs on getting *head-commit* line numbers right
from GitHub's bare per-file patches, so these assertions are exact.
"""
from __future__ import annotations

from app.analysis.diff_parser import (
    parse_file_patch,
    parse_unified_diff,
    ranges_from_lines,
)


def test_ranges_from_lines_collapses_contiguous():
    assert ranges_from_lines([2, 3, 4, 7, 8, 10]) == [(2, 4), (7, 8), (10, 10)]
    assert ranges_from_lines([]) == []
    assert ranges_from_lines([5]) == [(5, 5)]
    # unordered / duplicate input is normalized
    assert ranges_from_lines([10, 2, 3, 2, 4]) == [(2, 4), (10, 10)]


def test_parse_file_patch_maps_added_lines_to_head_numbers():
    # Hunk starts at head line 1, 6 lines in the new file.
    patch = (
        "@@ -1,4 +1,6 @@\n"
        " def foo():\n"
        "-    return 1\n"
        "+    # changed\n"
        "+    return 2\n"
        " \n"
        " def bar():\n"
    )
    fd = parse_file_patch("app/x.py", patch, "modified")

    # The two '+' lines are head lines 2 and 3.
    assert fd.added_lines == [2, 3]
    assert fd.added_ranges == [(2, 3)]
    # The removed line came from the *old* file, so it is a removed line.
    assert fd.removed_lines == [2]


def test_parse_file_patch_touches_and_contains():
    patch = (
        "@@ -10,3 +10,4 @@\n"
        " a = 1\n"
        "+b = 2\n"
        "+c = 3\n"
        " d = 4\n"
    )
    fd = parse_file_patch("m.py", patch, "modified")
    assert fd.added_lines == [11, 12]

    # touches(): does the finding's [start,end] overlap any added line?
    assert fd.touches(11, 11) is True
    assert fd.touches(9, 10) is False       # only context/unchanged lines
    assert fd.touches(12, 20) is True        # overlaps at 12
    assert fd.contains_added_line(12) is True
    assert fd.contains_added_line(13) is False


def test_parse_file_patch_added_file_status():
    # A brand-new file has no old side; every body line is added.
    patch = "@@ -0,0 +1,3 @@\n+import os\n+\n+X = 1\n"
    fd = parse_file_patch("new.py", patch, "added")
    assert fd.added_lines == [1, 2, 3]
    assert fd.added_ranges == [(1, 3)]


def test_parse_file_patch_no_patch_is_empty_not_crash():
    # Binary files / renames with no textual patch must not raise.
    fd = parse_file_patch("bin.dat", None, "modified")
    assert fd.added_lines == []
    assert fd.added_ranges == []
    assert fd.touches(1, 5) is False


def test_parse_unified_diff_multi_file():
    diff = (
        "diff --git a/one.py b/one.py\n"
        "--- a/one.py\n"
        "+++ b/one.py\n"
        "@@ -1,2 +1,3 @@\n"
        " x = 1\n"
        "+y = 2\n"
        " z = 3\n"
        "diff --git a/two.py b/two.py\n"
        "--- a/two.py\n"
        "+++ b/two.py\n"
        "@@ -5,2 +5,3 @@\n"
        " p = 1\n"
        "+q = 2\n"
        " r = 3\n"
    )
    diffs = parse_unified_diff(diff)
    assert set(diffs.keys()) == {"one.py", "two.py"}
    assert diffs["one.py"].added_lines == [2]
    assert diffs["two.py"].added_lines == [6]
