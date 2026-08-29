"""Repository registration + live PR browsing.

Repos enter the system ONLY through the registration endpoint here (there is no
auto-discovery with a PAT). Browsing open PRs is a live, read-only GitHub call
that is not persisted.
"""
from __future__ import annotations

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


@router.get("/{repository_id}/pulls", response_model=list[PullRequestOut])
def list_pulls(repository_id: int, db: Session = Depends(get_db)) -> list[PullRequestOut]:
    repo = db.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        with GitHubClient() as gh:
            live = list_open_pull_requests(gh, repo.owner, repo.name)
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    # Merge in local review state so the dashboard can gate the Review button.
    stored = {
        pr.number: pr
        for pr in db.scalars(
            select(PullRequest).where(PullRequest.repository_id == repo.id)
        )
    }

    out: list[PullRequestOut] = []
    for s in live:
        local = stored.get(s.number)
        latest = local.reviews[0] if (local and local.reviews) else None
        out.append(
            PullRequestOut(
                number=s.number,
                title=s.title,
                author=s.author,
                state=s.state,
                html_url=s.html_url,
                head_sha=s.head_sha,
                base_sha=s.base_sha,
                updated_at=s.updated_at,
                additions=s.additions,
                deletions=s.deletions,
                changed_files=s.changed_files,
                last_reviewed_sha=local.last_reviewed_sha if local else None,
                up_to_date=bool(local and local.last_reviewed_sha == s.head_sha),
                latest_review_id=latest.id if latest else None,
                latest_review_status=latest.status if latest else None,
            )
        )
    return out


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
