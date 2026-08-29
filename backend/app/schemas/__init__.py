"""Pydantic request/response schemas for the API layer."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----------------------------- repositories -----------------------------
class RepositoryCreate(BaseModel):
    url: str = Field(..., description="GitHub repo URL or 'owner/repo' shorthand")
    language: str = Field(default="python")


class RepositoryOut(ORMModel):
    id: int
    owner: str
    name: str
    full_name: str
    url: str
    default_branch: str | None
    language: str
    indexing_status: str
    indexed_at: datetime | None
    last_indexed_sha: str | None
    indexing_error: str | None
    created_at: datetime


# ------------------------------ pull requests ----------------------------
class PullRequestOut(BaseModel):
    """Live PR data merged with any locally-stored review state."""

    number: int
    title: str
    author: str | None
    state: str
    html_url: str
    head_sha: str
    base_sha: str | None
    updated_at: str | None
    additions: int
    deletions: int
    changed_files: int

    # Local review state (from the DB), used to gate the "Review" button.
    last_reviewed_sha: str | None = None
    up_to_date: bool = False           # True => head already reviewed, disable button
    latest_review_id: int | None = None
    latest_review_status: str | None = None


# --------------------------------- reviews -------------------------------
class ReviewTriggerRequest(BaseModel):
    repository_id: int
    pr_number: int
    force: bool = Field(
        default=False,
        description="Re-review even if head_sha == last_reviewed_sha.",
    )


class ReviewTriggerResponse(BaseModel):
    review_id: int
    status: str
    message: str


class VerificationOut(ORMModel):
    passed_deterministic: bool
    deterministic_checks: dict | None
    escalated: bool
    llm_verified: bool | None
    llm_reasoning: str | None
    final_verdict: str
    adjusted_confidence: float | None


class ReviewFindingOut(ORMModel):
    id: int
    file: str
    start_line: int
    end_line: int
    severity: str
    category: str
    title: str
    description: str
    evidence: str | None
    suggested_fix: str | None
    confidence: float
    verdict: str
    adjusted_confidence: float | None
    github_url: str | None
    verification: VerificationOut | None = None


class ChangedFileOut(ORMModel):
    filename: str
    status: str
    language: str | None
    additions: int
    deletions: int


class ReviewStatusOut(ORMModel):
    id: int
    status: str
    stage: str | None
    head_sha: str
    finding_count: int
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None


class ReviewDetailOut(ORMModel):
    id: int
    pull_request_id: int
    status: str
    stage: str | None
    head_sha: str
    summary: str | None
    error: str | None
    finding_count: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    findings: list[ReviewFindingOut] = []
    changed_files: list[ChangedFileOut] = []


# -------------------------------- feedback -------------------------------
class FeedbackCreate(BaseModel):
    verdict: str = Field(..., description="helpful | not_helpful | false_positive")
    comment: str | None = None
    reviewer: str | None = None


class FeedbackOut(ORMModel):
    id: int
    review_finding_id: int
    verdict: str
    comment: str | None
    reviewer: str | None
    created_at: datetime
