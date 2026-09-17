"""Repository registration + cached PR browsing.

Repos enter the system ONLY through the registration endpoint here. Cached PR
data is read from PostgreSQL; the explicit refresh endpoint fetches GitHub and
updates the cache.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import IndexingStatus
from app.github.client import GitHubClient, GitHubError, parse_repo_url
from app.github.pull_requests import list_open_pull_requests
from app.database import get_db
from app.models import PullRequest, Repository
from app.schemas import PullRequestOut, RepositoryCreate, RepositoryOut

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.post("", response_model=RepositoryOut, status_code=201)
def register_repository(payload: RepositoryCreate, db: Session = Depends(get_db)) -> Repository:
    try:
        ref = parse_repo_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = db.scalar(select(Repository).where(Repository.full_name == ref.full_name))
    if existing:
        # Idempotent: registering an already-known repo just returns it.
        return existing

    # Validate the PAT can actually read this repo before storing anything.
    try:
        with GitHubClient() as gh:
            meta = gh.check_access(ref.owner, ref.repo)
    except GitHubError as exc:
        status = 404 if exc.status_code == 404 else 403 if exc.status_code == 403 else 502
        raise HTTPException(status_code=status, detail=exc.message) from exc

    repo = Repository(
        owner=ref.owner,
        name=ref.repo,
        full_name=ref.full_name,
        url=meta.get("html_url") or f"https://github.com/{ref.full_name}",
        default_branch=meta.get("default_branch"),
        language=payload.language,
        indexing_status=IndexingStatus.NOT_STARTED.value,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


@router.get("", response_model=list[RepositoryOut])
def list_repositories(db: Session = Depends(get_db)) -> list[Repository]:
    return list(db.scalars(select(Repository).order_by(Repository.created_at.desc())))


@router.get("/{repository_id}", response_model=RepositoryOut)
def get_repository(repository_id: int, db: Session = Depends(get_db)) -> Repository:
    repo = db.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


def _pull_request_out(pr: PullRequest) -> PullRequestOut:
    latest = pr.reviews[0] if pr.reviews else None
    return PullRequestOut(
        number=pr.number,
        title=pr.title,
        author=pr.author,
        state=pr.state,
        html_url=pr.html_url,
        head_sha=pr.head_sha,
        base_sha=pr.base_sha,
        updated_at=pr.github_updated_at.isoformat() if pr.github_updated_at else None,
        additions=pr.additions,
        deletions=pr.deletions,
        changed_files=pr.changed_files,
        last_reviewed_sha=pr.last_reviewed_sha,
        up_to_date=bool(pr.last_reviewed_sha and pr.last_reviewed_sha == pr.head_sha),
        latest_review_id=latest.id if latest else None,
        latest_review_status=latest.status if latest else None,
    )


def _cached_open_pulls(repository_id: int, db: Session) -> list[PullRequestOut]:
    rows = db.scalars(
        select(PullRequest)
        .where(PullRequest.repository_id == repository_id, PullRequest.state == "open")
        .order_by(PullRequest.github_updated_at.desc())
    )
    return [_pull_request_out(pr) for pr in rows]


@router.get("/{repository_id}/pulls", response_model=list[PullRequestOut])
def list_pulls(repository_id: int, db: Session = Depends(get_db)) -> list[PullRequestOut]:
    repo = db.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return _cached_open_pulls(repo.id, db)


@router.post("/{repository_id}/pulls/refresh", response_model=list[PullRequestOut])
def refresh_pulls(repository_id: int, db: Session = Depends(get_db)) -> list[PullRequestOut]:
    repo = db.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        with GitHubClient() as gh:
            live = list_open_pull_requests(gh, repo.owner, repo.name)
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    stored = {
        pr.number: pr
        for pr in db.scalars(
            select(PullRequest).where(PullRequest.repository_id == repo.id)
        )
    }
    for summary in live:
        pr = stored.get(summary.number)
        if pr is None:
            pr = PullRequest(repository_id=repo.id, number=summary.number)
            db.add(pr)
        pr.title = summary.title
        pr.author = summary.author
        pr.state = summary.state
        pr.html_url = summary.html_url
        pr.head_sha = summary.head_sha
        pr.base_sha = summary.base_sha
        pr.github_updated_at = (
            datetime.fromisoformat(summary.updated_at.replace("Z", "+00:00"))
            if summary.updated_at
            else None
        )
        pr.additions = summary.additions
        pr.deletions = summary.deletions
        pr.changed_files = summary.changed_files

    live_numbers = {summary.number for summary in live}
    for pr in stored.values():
        if pr.number not in live_numbers:
            pr.state = "closed"
    db.commit()
    return _cached_open_pulls(repo.id, db)


@router.post("/{repository_id}/index", status_code=202)
def trigger_indexing(
    repository_id: int, background: BackgroundTasks, db: Session = Depends(get_db)
) -> dict:
    repo = db.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    if repo.indexing_status == IndexingStatus.INDEXING.value:
        raise HTTPException(status_code=409, detail="Indexing already in progress")

    repo.indexing_status = IndexingStatus.INDEXING.value
    repo.indexing_error = None
    db.commit()

    # Deferred import: keeps heavy RAG deps out of module import time.
    from app.indexing import run_indexing

    background.add_task(run_indexing, repository_id)
    return {"repository_id": repository_id, "status": IndexingStatus.INDEXING.value}
