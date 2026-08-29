"""A single authenticated, READ-ONLY GitHub REST client.

Uses the fine-grained PAT from settings. Every method here only ever issues GET
requests — there is no code path in this client that writes to GitHub.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

_REPO_URL_RE = re.compile(
    r"""^(?:https?://github\.com/|git@github\.com:)?   # optional host
        (?P<owner>[A-Za-z0-9_.-]+)/
        (?P<repo>[A-Za-z0-9_.-]+?)
        (?:\.git)?/?$""",
    re.VERBOSE,
)


class GitHubError(RuntimeError):
    """Raised for non-success GitHub responses, carrying the HTTP status."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_repo_url(url: str) -> RepoRef:
    """Parse ``owner/repo`` from a GitHub URL or ``owner/repo`` shorthand."""
    cleaned = url.strip()
    match = _REPO_URL_RE.match(cleaned)
    if not match:
        raise ValueError(f"Could not parse a GitHub owner/repo from: {url!r}")
    return RepoRef(owner=match.group("owner"), repo=match.group("repo"))


class GitHubClient:
    def __init__(self, token: str | None = None, base_url: str | None = None) -> None:
        self._token = token if token is not None else settings.github_token
        self._client = httpx.Client(
            base_url=base_url or settings.github_api_base,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                **({"Authorization": f"Bearer {self._token}"} if self._token else {}),
            },
            timeout=httpx.Timeout(30.0, read=60.0),
            follow_redirects=True,
        )

    # -- lifecycle --------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- low level --------------------------------------------------------
    def _get(self, path: str, *, accept: str | None = None, params: dict | None = None) -> httpx.Response:
        headers = {"Accept": accept} if accept else None
        resp = self._client.get(path, params=params, headers=headers)
        if resp.status_code >= 400:
            try:
                msg = resp.json().get("message", resp.text)
            except Exception:
                msg = resp.text
            raise GitHubError(resp.status_code, f"GitHub {resp.status_code}: {msg}")
        return resp

    def _paginate(self, path: str, params: dict | None = None) -> list[dict[str, Any]]:
        params = dict(params or {})
        params.setdefault("per_page", 100)
        page = 1
        out: list[dict[str, Any]] = []
        while True:
            params["page"] = page
            resp = self._get(path, params=params)
            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                break
            out.extend(batch)
            if len(batch) < params["per_page"]:
                break
            page += 1
        return out

    # -- repositories -----------------------------------------------------
    def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return self._get(f"/repos/{owner}/{repo}").json()

    def check_access(self, owner: str, repo: str) -> dict[str, Any]:
        """Validate the PAT can read the repo; returns repo metadata or raises."""
        return self.get_repo(owner, repo)

    def download_tarball(self, owner: str, repo: str, ref: str | None = None) -> bytes:
        """Download a gzipped tarball of the repo at ``ref`` (default branch if None).

        Used for full-repo indexing — far cheaper than fetching blobs one by one.
        """
        ref_part = f"/{ref}" if ref else ""
        resp = self._get(f"/repos/{owner}/{repo}/tarball{ref_part}")
        return resp.content

    def get_commit_sha(self, owner: str, repo: str, ref: str) -> str:
        """Resolve a branch/tag/ref to its current commit sha."""
        return self._get(f"/repos/{owner}/{repo}/commits/{ref}").json()["sha"]

    def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str | None:
        """Fetch a file's raw text at ``ref``; None if missing/binary/too large."""
        try:
            resp = self._get(
                f"/repos/{owner}/{repo}/contents/{path}",
                accept="application/vnd.github.raw",
                params={"ref": ref},
            )
        except GitHubError as exc:
            if exc.status_code in (404, 403):
                return None
            raise
        return resp.text

    # -- pull requests ----------------------------------------------------
    def list_open_pull_requests(self, owner: str, repo: str) -> list[dict[str, Any]]:
        return self._paginate(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": "open", "sort": "updated", "direction": "desc"},
        )

    def get_pull_request(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        return self._get(f"/repos/{owner}/{repo}/pulls/{number}").json()

    def get_pull_request_files(self, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
        """Per-file diff metadata: filename, status, additions, deletions, patch."""
        return self._paginate(f"/repos/{owner}/{repo}/pulls/{number}/files")

    def get_pull_request_diff(self, owner: str, repo: str, number: int) -> str:
        """The raw unified diff for the whole PR."""
        return self._get(
            f"/repos/{owner}/{repo}/pulls/{number}",
            accept="application/vnd.github.v3.diff",
        ).text
