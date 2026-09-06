import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../services/api";
import type { ReviewDetail, ReviewStatusOut } from "../types";
import ReviewSummary from "../components/ReviewSummary";
import FindingList from "../components/FindingList";
import { shortSha } from "../components/ui";

// The pipeline's stages, in order, for a progress indicator while running.
const STAGES = [
  "fetching diff",
  "static analysis",
  "retrieving context",
  "llm review",
  "verifying",
];

function StageProgress({ stage }: { stage: string | null }) {
  const current = stage ? STAGES.indexOf(stage) : -1;
  return (
    <div style={{ marginTop: 14 }}>
      {STAGES.map((s, i) => {
        const done = current > i;
        const active = current === i;
        return (
          <div key={s} className="stage-line" style={{ padding: "3px 0" }}>
            {done ? (
              <span style={{ color: "var(--green)" }}>✓</span>
            ) : active ? (
              <span className="spinner" />
            ) : (
              <span className="faint">○</span>
            )}
            <span className={done || active ? "" : "faint"}>{s}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function Review() {
  const { reviewId } = useParams();
  const id = Number(reviewId);
  const [status, setStatus] = useState<ReviewStatusOut | null>(null);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const stopPolling = () => {
    if (pollRef.current != null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const tick = useCallback(async () => {
    try {
      const s = await api.reviewStatus(id);
      setStatus(s);
      if (s.status === "done") {
        stopPolling();
        setDetail(await api.reviewDetail(id));
      } else if (s.status === "failed") {
        stopPolling();
      }
    } catch (e) {
      stopPolling();
      setErr(e instanceof ApiError ? e.detail : String(e));
    }
  }, [id]);

  useEffect(() => {
    if (!Number.isFinite(id)) {
      setErr("Invalid review id");
      return;
    }
    // Prime immediately, then poll until terminal.
    tick();
    pollRef.current = window.setInterval(tick, 1500);
    return stopPolling;
  }, [id, tick]);

  const running = status && (status.status === "queued" || status.status === "running");

  return (
    <div className="container">
      <Link to="/" className="back-link">
        ← Back to dashboard
      </Link>

      {err && <div className="error-banner">{err}</div>}

      {!status && !err && (
        <div className="stage-line">
          <span className="spinner" /> Loading review…
        </div>
      )}

      {running && (
        <div className="panel">
          <div className="panel-title-row">
            <h2>Review · {status!.status}</h2>
            <span className="faint small mono">{shortSha(status!.head_sha)}</span>
          </div>
          <div className="stage-line">
            <span className="spinner" />
            <span>
              {status!.status === "queued"
                ? "Queued — waiting for a worker…"
                : `Working: ${status!.stage ?? "…"}`}
            </span>
          </div>
          <StageProgress stage={status!.stage} />
          <p className="faint small" style={{ marginBottom: 0 }}>
            This page updates automatically. A review makes at most one main LLM
            call plus targeted verification, so it usually finishes in well under
            a minute.
          </p>
        </div>
      )}

      {status?.status === "failed" && (
        <div className="panel">
          <h2>Review #{id} · failed</h2>
          <div className="error-banner" style={{ marginBottom: 0 }}>
            {status.error || "The review failed without a specific error message."}
          </div>
        </div>
      )}

      {detail && detail.status === "done" && (
        <>
          <ReviewSummary review={detail} />
          <div className="panel">
            <div className="panel-title-row">
              <h2>Findings</h2>
              <span className="faint small mono">
                {detail.findings.length} surfaced @ {shortSha(detail.head_sha)}
              </span>
            </div>
            <FindingList findings={detail.findings} />
          </div>
        </>
      )}
    </div>
  );
}
