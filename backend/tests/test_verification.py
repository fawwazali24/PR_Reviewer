"""Tests for the verification layer: deterministic checks, confidence gate,
and the reviewer's finding normalization (plan Phases 5-6)."""
from __future__ import annotations

from app.analysis.diff_parser import parse_file_patch
from app.enums import VerificationVerdict
from app.llm.reviewer import _normalize
from app.llm.schemas import LLMFinding
from app.verification.confidence import should_surface
from app.verification.evidence import run_deterministic

# A file where the PR added head lines 11 and 12.
PATCH = (
    "@@ -10,3 +10,4 @@\n"
    " a = 1\n"
    "+b = 2\n"
    "+c = 3\n"
    " d = 4\n"
)

SOURCE = '''\
def handler():
    a = 1
    b = 2
    c = 3
    d = 4
    return a + b + c + d
'''


def _finding(**overrides) -> LLMFinding:
    base = dict(
        file="app/x.py",
        start_line=11,
        end_line=11,
        severity="medium",
        category="business_logic",
        title="t",
        description="d",
        evidence="e",
        confidence=0.7,
    )
    base.update(overrides)
    return LLMFinding(**base)


def _diffs():
    return {"app/x.py": parse_file_patch("app/x.py", PATCH, "modified")}


# --------------------------------------------------------------------------- #
# deterministic evidence
# --------------------------------------------------------------------------- #
def test_deterministic_passes_for_in_diff_finding():
    res = run_deterministic(
        _finding(start_line=11, end_line=12),
        file_diffs=_diffs(),
        head_sources={},  # no source -> soft checks are None, not failing
        semgrep=[],
    )
    assert res.passed is True
    assert res.checks["file_matches"] is True
    assert res.checks["line_in_diff"] is True


def test_deterministic_fails_when_file_not_changed():
    res = run_deterministic(
        _finding(file="app/other.py"),
        file_diffs=_diffs(),
        head_sources={},
        semgrep=[],
    )
    assert res.passed is False
    assert res.checks["file_matches"] is False


def test_deterministic_fails_when_line_outside_added_ranges():
    # Line 99 is a real-ish line but was not added/changed by this PR.
    res = run_deterministic(
        _finding(start_line=99, end_line=99),
        file_diffs=_diffs(),
        head_sources={},
        semgrep=[],
    )
    assert res.passed is False
    assert res.checks["line_in_diff"] is False


def test_deterministic_symbol_check_with_source():
    # With head source available, the finding's lines fall inside handler().
    res = run_deterministic(
        _finding(start_line=3, end_line=4),  # inside handler()
        file_diffs={"app/x.py": parse_file_patch(
            "app/x.py", "@@ -1,6 +1,6 @@\n def handler():\n-    a = 1\n+    a = 0\n", "modified",
        )},
        head_sources={"app/x.py": SOURCE},
        semgrep=[],
    )
    # symbol_exists resolves to True (line 3-4 is inside handler's span).
    assert res.checks["symbol_exists"] is True


# --------------------------------------------------------------------------- #
# confidence gate
# --------------------------------------------------------------------------- #
def test_rejected_findings_never_surface():
    assert should_surface(VerificationVerdict.REJECTED.value, 0.99) is False


def test_verified_finding_needs_to_clear_threshold():
    # Default CONFIDENCE_THRESHOLD is 0.55.
    assert should_surface(VerificationVerdict.VERIFIED.value, 0.9) is True
    assert should_surface(VerificationVerdict.VERIFIED.value, 0.10) is False


def test_uncertain_finding_gated_by_confidence_only():
    assert should_surface(VerificationVerdict.UNCERTAIN.value, 0.99) is True


# --------------------------------------------------------------------------- #
# reviewer normalization
# --------------------------------------------------------------------------- #
def test_normalize_coerces_bad_severity_and_category():
    f = _finding(severity="SHOWSTOPPER", category="nonsense")
    n = _normalize(f)
    assert n.severity == "medium"
    assert n.category == "maintainability"


def test_normalize_clamps_confidence_and_fixes_line_order():
    f = _finding(start_line=10, end_line=3, confidence=1.7)
    n = _normalize(f)
    assert n.confidence == 1.0
    assert n.end_line >= n.start_line


def test_normalize_preserves_valid_values():
    f = _finding(severity="high", category="security", confidence=0.42)
    n = _normalize(f)
    assert n.severity == "high"
    assert n.category == "security"
    assert n.confidence == 0.42
