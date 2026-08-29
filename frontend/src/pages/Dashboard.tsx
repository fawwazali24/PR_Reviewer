import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../services/api";
import type { Repository } from "../types";
import RepositoryForm from "../components/RepositoryForm";
import RepositoryList from "../components/RepositoryList";
import PullRequestList from "../components/PullRequestList";

export default function Dashboard() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const pollRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const repos = await api.listRepositories();
      setRepositories(repos);
      setErr(null);
      // Keep a selection if we can; otherwise default to the first repo.
      setSelectedId((cur) =>
        cur && repos.some((r) => r.id === cur) ? cur : repos[0]?.id ?? null
      );
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while any repo is actively indexing so the status dot updates live.
  useEffect(() => {
    const anyIndexing = repositories.some((r) => r.indexing_status === "indexing");
    if (anyIndexing && pollRef.current == null) {
      pollRef.current = window.setInterval(load, 3000);
    } else if (!anyIndexing && pollRef.current != null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current != null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [repositories, load]);

  const selected = repositories.find((r) => r.id === selectedId) ?? null;

  return (
    <div className="container wide">
      {err && <div className="error-banner">{err}</div>}

      <div className="panel">
        <h2>Add a repository</h2>
        <RepositoryForm
          onAdded={(repo) => {
            setSelectedId(repo.id);
            load();
          }}
        />
        <p className="faint small" style={{ marginBottom: 0, marginTop: 10 }}>
          Uses a read-only fine-grained token. This tool never writes to GitHub —
          every result stays on this dashboard.
        </p>
      </div>

      <div className="panel">
        <h2>Repositories</h2>
        {!loaded ? (
          <div className="stage-line">
            <span className="spinner" /> Loading…
          </div>
        ) : (
          <RepositoryList
            repositories={repositories}
            selectedId={selectedId}
            onSelect={(r) => setSelectedId(r.id)}
            onChanged={load}
          />
        )}
      </div>

      {selected && <PullRequestList key={selected.id} repo={selected} />}
    </div>
  );
}
