"""Higher-level PR fetching, normalizing GitHub's raw JSON into stable shapes.

Keeps the rest of the app decoupled from GitHub's response format.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.github.client import GitHubClient


@dataclass
class PullRequestFile:
    filename: str
    status: str                       # added | modified | removed | renamed
    additions: int
    deletions: int
    patch: str | None                 # unified-diff hunk (absent for binary files)
    previous_filename: str | None = None


@dataclass
class PullRequestSummary:
    number: int
    title: str
    author: str | None
    state: str
    html_url: str
    head_sha: str
    base_sha: str | None
    updated_at: str | None
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0


@dataclass
class PullRequestDetail:
    summary: PullRequestSummary
    description: str | None
    base_ref: str | None
    files: list[PullRequestFile] = field(default_factory=list)


def _summary_from_json(pr: dict[str, Any]) -> PullRequestSummary:
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    user = pr.get("user") or {}
    return PullRequestSummary(
        number=pr["number"],
        title=pr.get("title") or "",
        author=user.get("login"),
        state=pr.get("state") or "open",
        html_url=pr.get("html_url") or "",
        head_sha=head.get("sha") or "",
        base_sha=base.get("sha"),
        updated_at=pr.get("updated_at"),
        additions=pr.get("additions", 0) or 0,
        deletions=pr.get("deletions", 0) or 0,
        changed_files=pr.get("changed_files", 0) or 0,
    )


def list_open_pull_requests(
    client: GitHubClient, owner: str, repo: str
) -> list[PullRequestSummary]:
    """Live, read-only listing of open PRs (never persisted)."""
    return [_summary_from_json(pr) for pr in client.list_open_pull_requests(owner, repo)]


def get_pull_request_detail(
    client: GitHubClient, owner: str, repo: str, number: int
) -> PullRequestDetail:
    """Full PR metadata + per-file diffs for a specific PR."""
    pr = client.get_pull_request(owner, repo, number)
    summary = _summary_from_json(pr)
    base = pr.get("base") or {}

    files = [
        PullRequestFile(
            filename=f["filename"],
            status=f.get("status", "modified"),
            additions=f.get("additions", 0) or 0,
            deletions=f.get("deletions", 0) or 0,
            patch=f.get("patch"),
            previous_filename=f.get("previous_filename"),
        )
        for f in client.get_pull_request_files(owner, repo, number)
    ]

    return PullRequestDetail(
        summary=summary,
        description=pr.get("body"),
        base_ref=base.get("ref"),
        files=files,
    )
