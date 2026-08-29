"""Verification orchestration: deterministic-first, LLM-second (plan change #3).

Every finding runs the cheap deterministic checks. A finding that fails them is
rejected outright. A finding that passes but needs semantic judgment — chiefly
business-logic/security/cross-file claims that aren't already near-certain — is
escalated to a single cheap LLM verification call whose main job is to catch the
dominant failure mode: the reviewer flagged something the codebase already
handles. High-confidence or non-semantic findings skip the second call.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.analysis.diff_parser import FileDiff
from app.analysis.semgrep import SemgrepFinding
from app.config import settings
from app.enums import VerificationVerdict
from app.llm import prompts
from app.llm.client import LLMConfigError, generate_structured
from app.llm.reviewer import format_retrieved_sections, format_semgrep_section
from app.llm.schemas import LLMFinding, VerificationDecision
from app.rag.retriever import RetrievedChunk
from app.verification.evidence import run_deterministic

logger = logging.getLogger(__name__)

SEMANTIC_CATEGORIES = {"business_logic", "security", "cross_file"}
_ESCALATE_BELOW = 0.9        # semantic findings this confident or more skip the 2nd call
_CORROBORATION_BONUS = 0.1


@dataclass
class VerificationOutcome:
    passed_deterministic: bool
    deterministic_checks: dict
    escalated: bool
    llm_verified: bool | None
    llm_reasoning: str | None
    final_verdict: str
    adjusted_confidence: float


def _clamp(x: float) -> float:
    return min(1.0, max(0.0, x))


def _excerpt(source: str | None, start: int, end: int, pad: int = 4) -> str:
    if not source:
        return ""
    lines = source.splitlines()
    lo = max(1, start - pad)
    hi = min(len(lines), end + pad)
    numbered = [f"{i}: {lines[i - 1]}" for i in range(lo, hi + 1)]
    return "\n".join(numbered)


def _semantic_verify(
    finding: LLMFinding,
    *,
    retrieved: list[RetrievedChunk],
    semgrep: list[SemgrepFinding],
    head_sources: dict[str, str],
    verify_model: str | None,
) -> VerificationDecision:
    file_semgrep = [
        s for s in semgrep if s.path.endswith(finding.file) or finding.file.endswith(s.path)
    ]
    prompt = prompts.build_verification_prompt(
        finding_json=finding.model_dump_json(indent=2),
        diff_excerpt=_excerpt(head_sources.get(finding.file), finding.start_line, finding.end_line),
        retrieved_sections=format_retrieved_sections(retrieved),
        semgrep_section=format_semgrep_section(file_semgrep),
    )
    return generate_structured(
        prompt=prompt,
        system=prompts.VERIFICATION_SYSTEM_PROMPT,
        schema=VerificationDecision,
        model=verify_model or settings.gemini_verify_model,
        temperature=0.0,
    )


def verify_finding(
    finding: LLMFinding,
    *,
    file_diffs: dict[str, FileDiff],
    head_sources: dict[str, str],
    retrieved: list[RetrievedChunk],
    semgrep: list[SemgrepFinding],
    verify_model: str | None = None,
) -> VerificationOutcome:
    det = run_deterministic(
        finding, file_diffs=file_diffs, head_sources=head_sources, semgrep=semgrep
    )

    if not det.passed:
        return VerificationOutcome(
            passed_deterministic=False,
            deterministic_checks=det.checks,
            escalated=False,
            llm_verified=None,
            llm_reasoning="Failed deterministic checks (not attributable to this PR's diff).",
            final_verdict=VerificationVerdict.REJECTED.value,
            adjusted_confidence=min(finding.confidence, 0.2),
        )

    base_conf = finding.confidence
    if det.semgrep_corroborates:
        base_conf = _clamp(base_conf + _CORROBORATION_BONUS)

    needs_semantic = finding.category in SEMANTIC_CATEGORIES and base_conf < _ESCALATE_BELOW
    if not needs_semantic:
        return VerificationOutcome(
            passed_deterministic=True,
            deterministic_checks=det.checks,
            escalated=False,
            llm_verified=None,
            llm_reasoning=None,
            final_verdict=VerificationVerdict.VERIFIED.value,
            adjusted_confidence=base_conf,
        )

    try:
        decision = _semantic_verify(
            finding,
            retrieved=retrieved,
            semgrep=semgrep,
            head_sources=head_sources,
            verify_model=verify_model,
        )
    except LLMConfigError:
        raise
    except Exception as exc:  # verifier failed; keep finding but flag as uncertain
        logger.warning("semantic verification failed for %r: %s", finding.title, exc)
        return VerificationOutcome(
            passed_deterministic=True,
            deterministic_checks=det.checks,
            escalated=True,
            llm_verified=None,
            llm_reasoning=f"Verifier error: {exc}",
            final_verdict=VerificationVerdict.UNCERTAIN.value,
            adjusted_confidence=base_conf,
        )

    verdict = (
        VerificationVerdict.VERIFIED.value
        if decision.is_real
        else VerificationVerdict.REJECTED.value
    )
    return VerificationOutcome(
        passed_deterministic=True,
        deterministic_checks=det.checks,
        escalated=True,
        llm_verified=decision.is_real,
        llm_reasoning=decision.reasoning,
        final_verdict=verdict,
        adjusted_confidence=_clamp(decision.adjusted_confidence),
    )
