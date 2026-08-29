"""The on-demand review pipeline (Phases 3-7 wired together).

Runs as a background task started by ``POST /reviews/trigger``. Fetches the PR
diff, parses it, pulls head sources, runs Semgrep + Tree-sitter, retrieves
domain context, makes ONE review LLM call, verifies each finding
(deterministic-first), applies the confidence threshold, and persists results.

Its ONLY output is the database — nothing is ever written back to GitHub.

State is updated in short transactions as it progresses so the dashboard's
status poll reflects live progress; the heavy work (LLM, embeddings) happens
outside any open DB transaction.
"""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone

from app.analysis.diff_parser import FileDiff, parse_file_patch
from app.analysis.semgrep import SemgrepFinding, run_semgrep
from app.analysis.tree_sitter import enclosing_symbols
from app.config import settings
from app.enums import ReviewStatus
from app.github.client import GitHubClient
from app.github.pull_requests import get_pull_request_detail
from app.database import session_scope
from app.llm.client import LLMConfigError
from app.llm.reviewer import ChangedFileContext, ReviewContext, run_llm_review
from app.llm.schemas import LLMFinding
from app.models import (
    ChangedFile,
    PullRequest,
    Repository,
    Review,
    ReviewFinding,
    StaticAnalysisFinding,
    VerificationResult,
)
from app.rag.retriever import RetrievedChunk, retrieve_context
from app.verification.confidence import should_surface
from app.verification.verifier import verify_finding

logger = logging.getLogger(__name__)

_MAX_QUERY_CHARS = 2000
_MAX_QUERIES = 6


@dataclass
class _Job:
    review_id: int
    repository_id: int
    pull_request_id: int
    owner: str
    name: str
    number: int
    head_sha: str
    repo_url: str
    pr_title: str
    pr_description: str | None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _language_for(path: str) -> str | None:
    if path.endswith(".py"):
        return "python"
    return None


def _github_line_anchor(start: int, end: int) -> str:
    return f"#L{start}" if start == end else f"#L{start}-L{end}"


# --------------------------------------------------------------------------- #
# small state-transition helpers (each its own short transaction)
# --------------------------------------------------------------------------- #
def _load_job(review_id: int) -> _Job | None:
    with session_scope() as db:
        review = db.get(Review, review_id)
        if review is None:
            return None
        pr = db.get(PullRequest, review.pull_request_id)
        repo = db.get(Repository, pr.repository_id)
        return _Job(
            review_id=review.id,
            repository_id=repo.id,
            pull_request_id=pr.id,
            owner=repo.owner,
            name=repo.name,
            number=pr.number,
            head_sha=review.head_sha,
            repo_url=repo.url,
            pr_title=pr.title,
            pr_description=pr.description,
        )


def _set_stage(review_id: int, stage: str, *, running: bool = False) -> None:
    with session_scope() as db:
        review = db.get(Review, review_id)
        if review is None:
            return
        review.stage = stage
        if running and review.status != ReviewStatus.RUNNING.value:
            review.status = ReviewStatus.RUNNING.value
            review.started_at = _utcnow()


def _mark_failed(review_id: int, error: str) -> None:
    with session_scope() as db:
        review = db.get(Review, review_id)
        if review is None:
            return
        review.status = ReviewStatus.FAILED.value
        review.stage = "failed"
        review.error = error[:2000]
        review.completed_at = _utcnow()


# --------------------------------------------------------------------------- #
# main entry
# --------------------------------------------------------------------------- #
def run_review_pipeline(review_id: int) -> None:
    job = _load_job(review_id)
    if job is None:
        logger.warning("pipeline: review %s not found", review_id)
        return

    try:
        _set_stage(review_id, "fetching diff", running=True)
        with GitHubClient() as gh:
            detail = get_pull_request_detail(gh, job.owner, job.name, job.number)
            # Pull head sources for changed Python files (for Tree-sitter +
            # Semgrep + verification). Removed files are skipped.
            head_sources: dict[str, str] = {}
            for f in detail.files:
                if _language_for(f.filename) == "python" and f.status != "removed":
                    src = gh.get_file_content(job.owner, job.name, f.filename, job.head_sha)
                    if src is not None:
                        head_sources[f.filename] = src

        file_diffs: dict[str, FileDiff] = {}
        changed_contexts: list[ChangedFileContext] = []
        changed_rows: list[dict] = []
        for f in detail.files:
            fd = parse_file_patch(f.filename, f.patch, f.status)
            file_diffs[f.filename] = fd

            symbols: list[str] = []
            src = head_sources.get(f.filename)
            if src is not None and fd.added_ranges:
                symbols = [s.qualified_name for s in enclosing_symbols(src, fd.added_ranges)]

            changed_contexts.append(
                ChangedFileContext(
                    filename=f.filename,
                    status=f.status,
                    patch=f.patch,
                    enclosing_symbols=symbols,
                )
            )
            changed_rows.append(
                {
                    "filename": f.filename,
                    "previous_filename": f.previous_filename,
                    "status": f.status,
                    "language": _language_for(f.filename),
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "patch": f.patch,
                    "added_line_ranges": [list(r) for r in fd.added_ranges],
                }
            )

        _set_stage(review_id, "static analysis")
        semgrep = _run_semgrep_on_sources(head_sources)

        _set_stage(review_id, "retrieving context")
        patches = {c.filename: c.patch for c in changed_contexts}
        retrieved = _retrieve(job.repository_id, head_sources, file_diffs, patches)

        _set_stage(review_id, "llm review")
        context = ReviewContext(
            pr_title=job.pr_title,
            pr_description=job.pr_description,
            changed_files=changed_contexts,
            retrieved=retrieved,
            semgrep=semgrep,
        )
        review_output = run_llm_review(context)

        _set_stage(review_id, "verifying")
        outcomes = [
            (
                finding,
                verify_finding(
                    finding,
                    file_diffs=file_diffs,
                    head_sources=head_sources,
                    retrieved=retrieved,
                    semgrep=semgrep,
                ),
            )
            for finding in review_output.findings
        ]

        _persist_results(
            job=job,
            summary=review_output.summary,
            changed_rows=changed_rows,
            semgrep=semgrep,
            outcomes=outcomes,
        )
        logger.info("review %s complete (%s findings)", review_id, len(outcomes))

    except LLMConfigError as exc:
        _mark_failed(review_id, f"LLM not configured: {exc}")
    except Exception as exc:  # noqa: BLE001 - background task must not crash silently
        logger.exception("pipeline failed for review %s", review_id)
        _mark_failed(review_id, str(exc))


# --------------------------------------------------------------------------- #
# steps
# --------------------------------------------------------------------------- #
def _run_semgrep_on_sources(head_sources: dict[str, str]) -> list[SemgrepFinding]:
    """Materialize head sources to a temp dir and run Semgrep over them."""
    py = {p: s for p, s in head_sources.items() if p.endswith(".py")}
    if not py:
        return []
    with tempfile.TemporaryDirectory(prefix="prr_semgrep_") as tmp:
        rel_paths: list[str] = []
        for path, source in py.items():
            dest = os.path.join(tmp, path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(source)
            rel_paths.append(path)
        return run_semgrep(rel_paths, cwd=tmp)


def _added_lines_from_patch(patch: str | None) -> str:
    """Extract the added-line *content* from a unified-diff patch."""
    if not patch:
        return ""
    return "\n".join(
        line[1:]
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def _build_queries(
    head_sources: dict[str, str],
    file_diffs: dict[str, FileDiff],
    patches: dict[str, str | None],
) -> list[str]:
    """Query texts for retrieval: the changed functions' bodies where possible,
    otherwise the added-line content from the patch."""
    queries: list[str] = []
    for path, fd in file_diffs.items():
        src = head_sources.get(path)
        if src and fd.added_ranges:
            for sym in enclosing_symbols(src, fd.added_ranges):
                body = "\n".join(src.splitlines()[sym.start_line - 1 : sym.end_line])
                queries.append(body[:_MAX_QUERY_CHARS])
        else:
            # No source/symbols (non-Python or top-level change): use the patch.
            queries.append(_added_lines_from_patch(patches.get(path))[:_MAX_QUERY_CHARS])
    queries = [q for q in queries if q.strip()][:_MAX_QUERIES]
    return queries


def _retrieve(
    repository_id: int,
    head_sources: dict[str, str],
    file_diffs: dict[str, FileDiff],
    patches: dict[str, str | None],
) -> list[RetrievedChunk]:
    queries = _build_queries(head_sources, file_diffs, patches)
    if not queries:
        return []
    exclude = set(file_diffs.keys())
    try:
        with session_scope() as db:
            return retrieve_context(
                db, repository_id, queries, k=settings.retrieval_top_k, exclude_files=exclude
            )
    except Exception:  # retrieval is best-effort; a review still runs without it
        logger.exception("retrieval failed for repo %s", repository_id)
        return []


def _persist_results(
    *,
    job: _Job,
    summary: str,
    changed_rows: list[dict],
    semgrep: list[SemgrepFinding],
    outcomes: list[tuple[LLMFinding, object]],
) -> None:
    surfaced_count = 0
    with session_scope() as db:
        review = db.get(Review, job.review_id)
        if review is None:
            return

        for row in changed_rows:
            db.add(ChangedFile(review_id=review.id, **row))

        for s in semgrep:
            db.add(
                StaticAnalysisFinding(
                    review_id=review.id,
                    tool="semgrep",
                    rule_id=s.rule_id,
                    file_path=s.path,
                    start_line=s.start_line,
                    end_line=s.end_line,
                    severity=s.severity,
                    message=s.message,
                    raw=s.raw,
                )
            )

        for finding, outcome in outcomes:
            surfaced = should_surface(outcome.final_verdict, outcome.adjusted_confidence)
            surfaced_count += int(surfaced)
            github_url = (
                f"{job.repo_url}/blob/{job.head_sha}/{finding.file}"
                f"{_github_line_anchor(finding.start_line, finding.end_line)}"
            )
            rf = ReviewFinding(
                review_id=review.id,
                file=finding.file,
                start_line=finding.start_line,
                end_line=finding.end_line,
                severity=finding.severity,
                category=finding.category,
                title=finding.title,
                description=finding.description,
                evidence=finding.evidence,
                suggested_fix=finding.suggested_fix,
                confidence=finding.confidence,
                verdict=outcome.final_verdict,
                adjusted_confidence=outcome.adjusted_confidence,
                surfaced=surfaced,
                github_url=github_url,
            )
            db.add(rf)
            db.flush()  # get rf.id for the verification row
            db.add(
                VerificationResult(
                    review_finding_id=rf.id,
                    passed_deterministic=outcome.passed_deterministic,
                    deterministic_checks=outcome.deterministic_checks,
                    escalated=outcome.escalated,
                    llm_verified=outcome.llm_verified,
                    llm_reasoning=outcome.llm_reasoning,
                    final_verdict=outcome.final_verdict,
                    adjusted_confidence=outcome.adjusted_confidence,
                )
            )

        review.summary = summary
        review.finding_count = surfaced_count
        review.status = ReviewStatus.DONE.value
        review.stage = "done"
        review.completed_at = _utcnow()

        # Record the reviewed commit so the button can guard double-reviews.
        pr = db.get(PullRequest, job.pull_request_id)
        if pr is not None:
            pr.last_reviewed_sha = job.head_sha
