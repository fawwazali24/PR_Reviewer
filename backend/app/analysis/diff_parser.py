"""Unified-diff parsing with exact head-commit line mapping.

GitHub's per-file ``patch`` field is a bare set of hunks (no ``---/+++``
header). We synthesize a minimal header so the battle-tested ``unidiff`` parser
can compute precise new-file line numbers for added lines — the mapping every
downstream finding and GitHub deep-link anchors to, so it must be exact.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from unidiff import PatchSet


@dataclass
class FileDiff:
    filename: str
    status: str
    # New-file (head commit) line numbers that were added by this PR.
    added_lines: list[int] = field(default_factory=list)
    # Old-file line numbers that were removed.
    removed_lines: list[int] = field(default_factory=list)
    # Contiguous runs of added_lines, as inclusive (start, end) pairs.
    added_ranges: list[tuple[int, int]] = field(default_factory=list)

    def contains_added_line(self, line: int) -> bool:
        return any(start <= line <= end for start, end in self.added_ranges)

    def touches(self, start_line: int, end_line: int) -> bool:
        """True if [start_line, end_line] overlaps any added range."""
        return any(
            not (end_line < s or start_line > e) for s, e in self.added_ranges
        )


def ranges_from_lines(lines: list[int]) -> list[tuple[int, int]]:
    """Collapse a sorted-or-unsorted list of ints into contiguous ranges."""
    if not lines:
        return []
    ordered = sorted(set(lines))
    ranges: list[tuple[int, int]] = []
    start = prev = ordered[0]
    for n in ordered[1:]:
        if n == prev + 1:
            prev = n
        else:
            ranges.append((start, prev))
            start = prev = n
    ranges.append((start, prev))
    return ranges


def parse_file_patch(filename: str, patch: str | None, status: str = "modified") -> FileDiff:
    """Parse one file's GitHub ``patch`` into added/removed line numbers."""
    fd = FileDiff(filename=filename, status=status)
    if not patch:
        return fd

    # unidiff needs a file header; synthesize a minimal one.
    synthetic = f"--- a/{filename}\n+++ b/{filename}\n{patch}\n"
    try:
        patch_set = PatchSet(io.StringIO(synthetic))
    except Exception:
        return fd

    for patched_file in patch_set:
        for hunk in patched_file:
            for line in hunk:
                if line.is_added and line.target_line_no is not None:
                    fd.added_lines.append(line.target_line_no)
                elif line.is_removed and line.source_line_no is not None:
                    fd.removed_lines.append(line.source_line_no)

    fd.added_ranges = ranges_from_lines(fd.added_lines)
    return fd


def parse_unified_diff(diff: str) -> dict[str, FileDiff]:
    """Parse a whole-PR unified diff into ``{filename: FileDiff}``."""
    out: dict[str, FileDiff] = {}
    try:
        patch_set = PatchSet(io.StringIO(diff))
    except Exception:
        return out

    for patched_file in patch_set:
        name = patched_file.path
        status = (
            "added" if patched_file.is_added_file
            else "removed" if patched_file.is_removed_file
            else "renamed" if patched_file.is_rename
            else "modified"
        )
        fd = FileDiff(filename=name, status=status)
        for hunk in patched_file:
            for line in hunk:
                if line.is_added and line.target_line_no is not None:
                    fd.added_lines.append(line.target_line_no)
                elif line.is_removed and line.source_line_no is not None:
                    fd.removed_lines.append(line.source_line_no)
        fd.added_ranges = ranges_from_lines(fd.added_lines)
        out[name] = fd
    return out
