import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../services/api";
import type { PullRequest, Repository } from "../types";
import { fmtTime, shortSha } from "./ui";

// Live open PRs for the selected repo (a read-only GitHub call, not persisted).
// The "Review" button is gated on `up_to_date` so we never burn an LLM call
// re-reviewing an unchanged commit; a force re-review is still one click away.
export default function PullRequestList({ repo }: { repo: Repository }) {
  const navigate = useNavigate();
  const [pulls, setPulls] = useState<PullRequest[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busyNumber, setBusyNumber] = useState<number | null>(null);
  const [forceFor, setForceFor] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setPulls(await api.listPulls(repo.id));
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
      setPulls([]);
    } finally {
      setLoading(false);
    }
  }, [repo.id]);

  useEffect(() => {
    load();
  }, [load]);

  const review = async (pr: PullRequest, force = false) => {
    setBusyNumber(pr.number);
    setErr(null);
    setForceFor(null);
    try {
      const res = await api.triggerReview(repo.id, pr.number, force);
      navigate(`/reviews/${res.review_id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        // Already reviewed at this commit — offer a forced re-review.
        setForceFor(pr.number);
        setErr(e.detail);
      } else {
        setErr(e instanceof ApiError ? e.detail : String(e));
      }
    } finally {
      setBusyNumber(null);
    }
  };

  return (
    <div className="panel">
      <div className="panel-title-row">
        <h2>Open pull requests · {repo.full_name}</h2>
        <button className="ghost small" onClick={load} disabled={loading}>
          {loading ? "loading…" : "refresh"}
        </button>
      </div>

      {err && <div className="error-banner">{err}</div>}

      {loading && !pulls && (
        <div className="stage-line">
          <span className="spinner" /> Fetching open PRs from GitHub…
        </div>
      )}

      {pulls && pulls.length === 0 && !loading && (
        <div className="empty">No open pull requests on this repository.</div>
      )}

      {pulls &&
        pulls.map((pr) => {
          const busy = busyNumber === pr.number;
          const reviewed = pr.up_to_date;
          const inProgress =
            pr.latest_review_status === "queued" ||
            pr.latest_review_status === "running";
          return (
            <div key={pr.number} className="list-item" style={{ cursor: "default" }}>
              <div className="grow">
                <div className="title">
                  <a href={pr.html_url} target="_blank" rel="noreferrer">
                    #{pr.number}
                  </a>{" "}
                  {pr.title}
                </div>
                <div className="sub">
                  {pr.author ? `@${pr.author} · ` : ""}
                  <span className="mono">{shortSha(pr.head_sha)}</span> ·{" "}
                  <span style={{ color: "var(--green)" }}>+{pr.additions}</span>{" "}
                  <span style={{ color: "var(--red)" }}>−{pr.deletions}</span> ·{" "}
                  {pr.changed_files} file{pr.changed_files === 1 ? "" : "s"}
                  {pr.updated_at ? ` · updated ${fmtTime(pr.updated_at)}` : ""}
                </div>
              </div>

              {reviewed && <span className="chip">up to date</span>}
              {inProgress && <span className="chip">review {pr.latest_review_status}</span>}

              {pr.latest_review_id && (
                <button
                  className="small"
                  onClick={() => navigate(`/reviews/${pr.latest_review_id}`)}
                >
                  {reviewed ? "view review" : "view last"}
                </button>
              )}

              {forceFor === pr.number ? (
                <button
                  className="small"
                  onClick={() => review(pr, true)}
                  disabled={busy}
                >
                  {busy ? "…" : "force re-review"}
                </button>
              ) : (
                <button
                  className="primary small"
                  onClick={() => review(pr, false)}
                  disabled={busy || reviewed}
                  title={
                    reviewed
                      ? "This commit was already reviewed"
                      : "Run an AI review on this PR's head commit"
                  }
                >
                  {busy ? "queuing…" : reviewed ? "reviewed" : "Review"}
                </button>
              )}
            </div>
          );
        })}
    </div>
  );
}
