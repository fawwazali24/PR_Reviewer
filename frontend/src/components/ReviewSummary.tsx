import type { ReviewDetail } from "../types";
import { fmtTime, shortSha } from "./ui";

// Top-of-review summary: the reviewer's overall take, the reviewed commit, the
// changed-file roster, and severity counts.
export default function ReviewSummary({ review }: { review: ReviewDetail }) {
  const counts = review.findings.reduce<Record<string, number>>((acc, f) => {
    acc[f.severity] = (acc[f.severity] || 0) + 1;
    return acc;
  }, {});
  const order = ["critical", "high", "medium", "low", "info"];

  return (
    <div className="panel">
      <div className="panel-title-row">
        <h2>Review summary</h2>
        <span className="faint small mono">
          {shortSha(review.head_sha)} · {fmtTime(review.completed_at)}
        </span>
      </div>

      {review.summary ? (
        <p style={{ marginTop: 0 }}>{review.summary}</p>
      ) : (
        <p className="muted" style={{ marginTop: 0 }}>
          No overall summary was produced.
        </p>
      )}

      <div className="row" style={{ gap: 8, flexWrap: "wrap", marginTop: 12 }}>
        <span className="chip">
          {review.finding_count} surfaced finding
          {review.finding_count === 1 ? "" : "s"}
        </span>
        {order
          .filter((s) => counts[s])
          .map((s) => (
            <span key={s} className={`chip sev sev-${s}`}>
              {counts[s]} {s}
            </span>
          ))}
      </div>

      {review.changed_files.length > 0 && (
        <>
          <h4
            style={{
              fontSize: 11,
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              color: "var(--text-faint)",
              margin: "18px 0 8px",
            }}
          >
            Changed files ({review.changed_files.length})
          </h4>
          <div>
            {review.changed_files.map((f) => (
              <div
                key={f.filename}
                className="row small"
                style={{ gap: 10, padding: "3px 0" }}
              >
                <span className="mono grow" style={{ minWidth: 0 }}>
                  {f.filename}
                </span>
                <span className="faint">{f.status}</span>
                <span style={{ color: "var(--green)" }}>+{f.additions}</span>
                <span style={{ color: "var(--red)" }}>−{f.deletions}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
