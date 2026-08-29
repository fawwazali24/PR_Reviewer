"""Canonical string constants for status/severity/category fields.

We deliberately store these as plain ``String`` columns (not native PG enums)
so schema changes don't require enum-type migrations. These classes are the
single source of truth for valid values, used by both models and API schemas.
"""
from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """String-valued enum whose members compare/serialize as their value."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class IndexingStatus(StrEnum):
    NOT_STARTED = "not_started"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"


class ReviewStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingCategory(StrEnum):
    """The judgment categories this system is actually here to add value on.

    (Syntax/style/known-vuln-patterns are left to CI — see the README.)
    """

    BUSINESS_LOGIC = "business_logic"   # intent vs. implementation, domain rules
    SECURITY = "security"               # context-dependent, not pattern-matchable
    CROSS_FILE = "cross_file"           # a change here breaks an assumption there
    MAINTAINABILITY = "maintainability"
    TEST_COVERAGE = "test_coverage"


class VerificationVerdict(StrEnum):
    VERIFIED = "verified"     # survived deterministic (+ optional semantic) checks
    REJECTED = "rejected"     # failed a hard check or refuted by the verifier
    UNCERTAIN = "uncertain"   # ambiguous; kept but flagged


class FeedbackVerdict(StrEnum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    FALSE_POSITIVE = "false_positive"


# Severity ordering for sorting findings most-severe first.
SEVERITY_ORDER: dict[str, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}
