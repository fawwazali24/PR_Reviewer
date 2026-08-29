"""Assemble review context and run the single review LLM call.

Takes the PR description + diffs + Tree-sitter symbol context + RAG-retrieved
domain context + Semgrep corroboration, calls Gemini once, and returns
schema-validated, normalized findings (retrying once on a parse/format error).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.analysis.semgrep import SemgrepFinding
from app.llm import prompts
from app.llm.client import generate_structured
from app.llm.schemas import LLMFinding, LLMReviewOutput
from app.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

_MAX_PATCH_CHARS = 6000
_MAX_CHUNK_CHARS = 1500

_ALLOWED_SEVERITIES = set(prompts.ALLOWED_SEVERITIES)
_ALLOWED_CATEGORIES = set(prompts.ALLOWED_CATEGORIES)


@dataclass
class ChangedFileContext:
    filename: str
    status: str
    patch: str | None
    enclosing_symbols: list[str] = field(default_factory=list)


@dataclass
class ReviewContext:
    pr_title: str
    pr_description: str | None
    changed_files: list[ChangedFileContext]
    retrieved: list[RetrievedChunk]
    semgrep: list[SemgrepFinding]


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n... [truncated]"


def format_changed_sections(files: list[ChangedFileContext]) -> str:
    blocks: list[str] = []
    for f in files:
        symbols = f", symbols: {', '.join(f.enclosing_symbols)}" if f.enclosing_symbols else ""
        header = f"## {f.filename} ({f.status}{symbols})"
        body = _truncate(f.patch or "(no textual diff)", _MAX_PATCH_CHARS)
        blocks.append(f"{header}\n```diff\n{body}\n```")
    return "\n\n".join(blocks)


def format_retrieved_sections(chunks: list[RetrievedChunk]) -> str:
    blocks: list[str] = []
    for c in chunks:
        tags = []
        if c.is_test:
            tags.append("test")
        if c.is_validation:
            tags.append("validation/rule")
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        name = c.symbol_name or "module"
        header = f"## {c.file_path}::{name} (lines {c.start_line}-{c.end_line}){tag_str}"
        blocks.append(f"{header}\n```python\n{_truncate(c.content, _MAX_CHUNK_CHARS)}\n```")
    return "\n\n".join(blocks)


def format_semgrep_section(findings: list[SemgrepFinding]) -> str:
    if not findings:
        return ""
    lines = [
        f"- {f.rule_id} @ {f.path}:{f.start_line} "
        f"[{f.severity or 'info'}] {f.message or ''}".strip()
        for f in findings
    ]
    return "\n".join(lines)


def _normalize(finding: LLMFinding) -> LLMFinding:
    severity = (finding.severity or "").strip().lower()
    if severity not in _ALLOWED_SEVERITIES:
        severity = "medium"
    category = (finding.category or "").strip().lower()
    if category not in _ALLOWED_CATEGORIES:
        category = "maintainability"
    start = max(1, finding.start_line)
    end = max(start, finding.end_line)
    confidence = min(1.0, max(0.0, finding.confidence))
    return finding.model_copy(
        update={
            "severity": severity,
            "category": category,
            "start_line": start,
            "end_line": end,
            "confidence": confidence,
        }
    )


def run_llm_review(context: ReviewContext, *, model: str | None = None) -> LLMReviewOutput:
    prompt = prompts.build_review_prompt(
        pr_title=context.pr_title,
        pr_description=context.pr_description,
        changed_sections=format_changed_sections(context.changed_files),
        retrieved_sections=format_retrieved_sections(context.retrieved),
        semgrep_section=format_semgrep_section(context.semgrep),
    )

    last_exc: Exception | None = None
    for attempt in range(2):  # one retry on format/parse failure
        try:
            output = generate_structured(
                prompt=prompt,
                system=prompts.SYSTEM_PROMPT,
                schema=LLMReviewOutput,
                model=model,
            )
            output.findings = [_normalize(f) for f in output.findings]
            return output
        except Exception as exc:  # LLMError etc. LLMConfigError is not retried below.
            from app.llm.client import LLMConfigError

            if isinstance(exc, LLMConfigError):
                raise
            last_exc = exc
            logger.warning("review LLM attempt %s failed: %s", attempt + 1, exc)

    raise last_exc if last_exc else RuntimeError("review failed")
