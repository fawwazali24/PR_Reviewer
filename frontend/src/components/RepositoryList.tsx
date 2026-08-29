import { useState } from "react";
import { api, ApiError } from "../services/api";
import type { IndexingStatus, Repository } from "../types";
import { fmtTime, shortSha } from "./ui";

const STATUS_DOT: Record<IndexingStatus, string> = {
  not_started: "idle",
  indexing: "busy",
  indexed: "ok",
  failed: "err",
};

const STATUS_LABEL: Record<IndexingStatus, string> = {
  not_started: "not indexed",
  indexing: "indexing…",
  indexed: "indexed",
  failed: "index failed",
};

// The registered-repos list. Selecting one drives the PR list. Each repo can be
// indexed for RAG context (optional but improves review quality).
export default function RepositoryList({
  repositories,
  selectedId,
  onSelect,
  onChanged,
}: {
  repositories: Repository[];
  selectedId: number | null;
  onSelect: (repo: Repository) => void;
  onChanged: () => void;
}) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const index = async (e: React.MouseEvent, repo: Repository) => {
    e.stopPropagation();
    setBusyId(repo.id);
    setErr(null);
    try {
      await api.indexRepository(repo.id);
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusyId(null);
    }
  };

  if (repositories.length === 0) {
    return <div className="empty">No repositories yet. Add one above to begin.</div>;
  }

  return (
    <div>
      {err && <div className="error-banner">{err}</div>}
      {repositories.map((repo) => {
        const selected = repo.id === selectedId;
        const status = repo.indexing_status;
        return (
          <div
            key={repo.id}
            className={`list-item ${selected ? "selected" : ""}`}
            onClick={() => onSelect(repo)}
          >
            <div className="grow">
              <div className="title">{repo.full_name}</div>
              <div className="sub">
                <span className={`dot ${STATUS_DOT[status]}`} />{" "}
                {STATUS_LABEL[status]}
                {status === "indexed" && repo.last_indexed_sha && (
                  <> · {shortSha(repo.last_indexed_sha)} · {fmtTime(repo.indexed_at)}</>
                )}
                {status === "failed" && repo.indexing_error && (
                  <span className="faint"> · {repo.indexing_error.slice(0, 80)}</span>
                )}
              </div>
            </div>
            <button
              className="small"
              onClick={(e) => index(e, repo)}
              disabled={busyId === repo.id || status === "indexing"}
              title="Index the repository for domain-aware retrieval"
            >
              {status === "indexing" || busyId === repo.id
                ? "indexing…"
                : status === "indexed"
                ? "re-index"
                : "index"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
