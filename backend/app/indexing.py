"""Full-repo indexing (Phase 4 entrypoint).

Downloads the repo tarball at its default branch (read-only), chunks every
Python file, embeds the chunks (reusing embeddings for unchanged content), and
writes them to pgvector. Runs as a background task; updates the repo's
indexing_status so the dashboard can reflect progress.
"""
from __future__ import annotations

import io
import logging
import tarfile

from app.config import settings
from app.enums import IndexingStatus
from app.github.client import GitHubClient
from app.database import session_scope
from app.models import Repository
from app.rag.chunker import ChunkData, chunk_file
from app.rag.vector_store import upsert_repository_chunks

logger = logging.getLogger(__name__)

_MAX_FILE_BYTES = 500_000
_SKIP_DIR_PARTS = {
    ".git", "node_modules", "venv", ".venv", "site-packages",
    "dist", "build", "__pycache__", ".tox", ".mypy_cache",
}


def _iter_python_files(tar_bytes: bytes):
    """Yield (repo_relative_path, source) for each Python file in the tarball."""
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.endswith(".py"):
                continue
            if member.size > _MAX_FILE_BYTES:
                continue
            # Tarball entries are prefixed with a top-level "owner-repo-sha/" dir.
            parts = member.name.split("/", 1)
            rel = parts[1] if len(parts) == 2 else member.name
            if any(part in _SKIP_DIR_PARTS for part in rel.split("/")):
                continue
            fh = tar.extractfile(member)
            if fh is None:
                continue
            try:
                source = fh.read().decode("utf-8", "replace")
            except Exception:
                continue
            yield rel, source


def run_indexing(repository_id: int) -> None:
    """Index (or re-index) one repository. Safe to call as a background task."""
    try:
        with session_scope() as db:
            repo = db.get(Repository, repository_id)
            if repo is None:
                logger.warning("indexing: repo %s not found", repository_id)
                return
            repo.indexing_status = IndexingStatus.INDEXING.value
            repo.indexing_error = None

            owner = repo.owner
            name = repo.name
            branch = repo.default_branch
            repo_language = repo.language

        with GitHubClient() as gh:
            ref = branch or gh.get_repo(owner, name).get("default_branch")
            head_sha = gh.get_commit_sha(owner, name, ref) if ref else None
            tar_bytes = gh.download_tarball(owner, name, ref)

        chunks: list[ChunkData] = []
        if repo_language == "python":
            for rel_path, source in _iter_python_files(tar_bytes):
                chunks.extend(chunk_file(rel_path, source))
        else:
            logger.warning(
                "indexing: language %r not supported yet (MVP is Python-only)",
                repo_language,
            )

        with session_scope() as db:
            stats = upsert_repository_chunks(db, repository_id, chunks)
            repo = db.get(Repository, repository_id)
            repo.indexing_status = IndexingStatus.INDEXED.value
            repo.last_indexed_sha = head_sha
            from datetime import datetime, timezone

            repo.indexed_at = datetime.now(timezone.utc)
            repo.indexing_error = None

        logger.info("indexing complete for %s/%s: %s", owner, name, stats)

    except Exception as exc:  # noqa: BLE001 - background task must not crash silently
        logger.exception("indexing failed for repo %s", repository_id)
        with session_scope() as db:
            repo = db.get(Repository, repository_id)
            if repo is not None:
                repo.indexing_status = IndexingStatus.FAILED.value
                repo.indexing_error = str(exc)[:1000]