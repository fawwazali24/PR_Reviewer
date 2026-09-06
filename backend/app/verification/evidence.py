"""Deterministic evidence checks — the cheap first line of verification.

These are pure functions over the finding + the PR's diffs + (when available)
the head-commit source of the changed file. They answer mechanical questions
with plain code so we don't waste a second LLM call on them:

  file_matches      finding points at a file the PR actually changed
  line_in_diff      finding's lines overlap the PR's ADDED lines (PR attribution)
  lines_valid       finding's lines exist in the head file
  symbol_exists     finding's lines fall inside a real function/class (not noise)
  semgrep_*         whether Semgrep corroborates on the same span

A check that can't be evaluated (e.g. no source available) returns None and is
treated as "not disqualifying", never as a failure.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.analysis.diff_parser import FileDiff
from app.analysis.semgrep import SemgrepFinding
from app.analysis.tree_sitter import parse_symbols
from app.llm.schemas import LLMFinding


@dataclass
class DeterministicResult:
    passed: bool
    checks: dict
    semgrep_corroborates: bool


def file_matches(finding_file: str, changed_files: set[str]) -> bool:
    return finding_file in changed_files


def line_in_diff(finding: LLMFinding, file_diffs: dict[str, FileDiff]) -> bool:
    fd = file_diffs.get(finding.file)
    if fd is None:
        return False
    return fd.touches(finding.start_line, finding.end_line)


def lines_valid(source: str | None, start: int, end: int) -> bool | None:
    if source is None:
        return None
    total = len(source.splitlines())
    return 1 <= start <= end <= total


def symbol_exists(source: str | None, start: int, end: int) -> bool | None:
    """True if [start,end] intersects a parsed function/class span."""
    if source is None:
        return None
    try:
        symbols = parse_symbols(source)
    except Exception:
        return None
    if not symbols:
        return None
    return any(not (s.end_line < start or s.start_line > end) for s in symbols)


def semgrep_corroborates(finding: LLMFinding, semgrep: list[SemgrepFinding]) -> bool:
    for s in semgrep:
        if s.path.endswith(finding.file) or finding.file.endswith(s.path):
            if not (s.end_line < finding.start_line or s.start_line > finding.end_line):
                return True
    return False


def run_deterministic(
    finding: LLMFinding,
    *,
    file_diffs: dict[str, FileDiff],
    head_sources: dict[str, str],
    semgrep: list[SemgrepFinding],
) -> DeterministicResult:
    changed = set(file_diffs.keys())
    source = head_sources.get(finding.file)

    checks = {
        "file_matches": file_matches(finding.file, changed),
        "line_in_diff": line_in_diff(finding, file_diffs),
        "lines_valid": lines_valid(source, finding.start_line, finding.end_line),
        "symbol_exists": symbol_exists(source, finding.start_line, finding.end_line),
    }
    corroborates = semgrep_corroborates(finding, semgrep)
    checks["semgrep_corroborates"] = corroborates

    # Hard requirements: the finding must point at a real added/changed line.
    # Soft checks (lines_valid / symbol_exists) only fail when explicitly False.
    passed = (
        checks["file_matches"]
        and checks["line_in_diff"]
        and checks["lines_valid"] is not False
        and checks["symbol_exists"] is not False
    )
    return DeterministicResult(passed=passed, checks=checks, semgrep_corroborates=corroborates)
