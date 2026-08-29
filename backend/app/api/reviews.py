"""On-demand review triggering + result retrieval.

Reviews run ONLY when triggered here (no scheduler, no polling loop). The
trigger guards against re-reviewing an unchanged commit (plan change #5) and
then enqueues the pipeline as a background task, returning immediately.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import SEVERITY_ORDER, ReviewStatus
from app.github.client import GitHubClient, GitHubError
from app.database import get_db
from app.models import PullRequest, Repository, Review
from app.schemas import (
    ReviewDetailOut,
    ReviewFindingOut,
    ReviewStatusOut,
    ReviewTriggerRequest,
    ReviewTriggerResponse,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/trigger", response_model=ReviewTriggerResponse, status_code=202)
def trigger_review(
    payload: ReviewTriggerRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ReviewTriggerResponse:
    repo = db.get(Repository, payload.repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Fetch current PR metadata (read-only) to learn the live head sha.
    try:
        with GitHubClient() as gh:
            pr_json = gh.get_pull_request(repo.owner, repo.name, payload.pr_number)
    except GitHubError as exc:
        status = 404 if exc.status_code == 404 else 502
        raise HTTPException(status_code=status, detail=exc.message) from exc

    head = pr_json.get("head") or {}
    base = pr_json.get("base") or {}
    user = pr_json.get("user") or {}
    head_sha = head.get("sha") or ""
    if not head_sha:
        raise HTTPException(status_code=502, detail="PR has no head sha")

    # Upsert the PullRequest row (a PR is persisted the moment it's reviewed).
    pr = db.scalar(
        select(PullRequest).where(
            PullRequest.repository_id == repo.id,
            PullRequest.number == payload.pr_number,
        )
    )
    if pr is None:
        pr = PullRequest(repository_id=repo.id, number=payload.pr_number)
        db.add(pr)
    pr.title = pr_json.get("title") or ""
    pr.description = pr_json.get("body")
    pr.author = user.get("login")
    pr.state = pr_json.get("state") or "open"
    pr.html_url = pr_json.get("html_url") or f"{repo.url}/pull/{payload.pr_number}"
    pr.head_sha = head_sha
    pr.base_sha = base.get("sha")
    pr.base_ref = base.get("ref")
    db.flush()

    # Guard: don't burn an LLM call re-reviewing an unchanged commit.
    if pr.last_reviewed_sha == head_sha and not payload.force:
        raise HTTPException(
            status_code=409,
            detail=(
                f"PR #{payload.pr_number} head {head_sha[:7]} was already reviewed. "
                "Pass force=true to re-review the same commit."
            ),
        )

    review = Review(
        pull_request_id=pr.id,
        head_sha=head_sha,
        status=ReviewStatus.QUEUED.value,
        stage="queued",
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    # Deferred import keeps heavy pipeline deps out of module import time.
    from app.pipeline import run_review_pipeline

    background.add_task(run_review_pipeline, review.id)

    return ReviewTriggerResponse(
        review_id=review.id,
        status=review.status,
        message=f"Review queued for PR #{payload.pr_number} @ {head_sha[:7]}",
    )


@router.get("/{review_id}/status", response_model=ReviewStatusOut)
def review_status(review_id: int, db: Session = Depends(get_db)) -> Review:
    """Lightweight status poll — a DB read, never a pipeline re-run."""
    review = db.get(Review, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@router.get("/{review_id}", response_model=ReviewDetailOut)
def review_detail(review_id: int, db: Session = Depends(get_db)) -> ReviewDetailOut:
    review = db.get(Review, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    surfaced = [f for f in review.findings if f.surfaced]
    surfaced.sort(
        key=lambda f: (
            SEVERITY_ORDER.get(f.severity, 99),
            -(f.adjusted_confidence if f.adjusted_confidence is not None else f.confidence),
        )
    )

    return ReviewDetailOut(
        id=review.id,
        pull_request_id=review.pull_request_id,
        status=review.status,
        stage=review.stage,
        head_sha=review.head_sha,
        summary=review.summary,
        error=review.error,
        finding_count=review.finding_count,
        started_at=review.started_at,
        completed_at=review.completed_at,
        created_at=review.created_at,
        findings=[ReviewFindingOut.model_validate(f) for f in surfaced],
        changed_files=review.changed_files,
    )
