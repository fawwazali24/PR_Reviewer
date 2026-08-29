import { useState } from "react";
import type { FeedbackVerdict, ReviewFinding } from "../types";
import { api, ApiError } from "../services/api";
import { CategoryChip, ConfidenceBar, SeverityBadge } from "./ui";
import JsonViewer from "./JsonViewer";

// Full detail for one finding: the reviewer's comment, the concrete evidence,
// an optional suggested fix, the verification trail, a working GitHub deep-link,
// the raw JSON, and a lightweight feedback control.
export default function FindingDetails({ finding }: { finding: ReviewFinding }) {
  const [sent, setSent] = useState<FeedbackVerdict | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const v = finding.verification;

  const sendFeedback = async (verdict: FeedbackVerdict) => {
    setErr(null);
    try {
      await api.submitFeedback(finding.id, verdict);
      setSent(verdict);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
    }
  };

  const conf =
    finding.adjusted_confidence != null
      ? finding.adjusted_confidence
      : finding.confidence;

  return (
    <div className="finding-body">
      <h4>Reviewer's comment</h4>
      <p>{finding.description}</p>

      {finding.evidence && (
        <>
          <h4>Evidence</h4>
          <p className="mono small">{finding.evidence}</p>
        </>
      )}

      {finding.suggested_fix && (
        <>
          <h4>Suggested direction</h4>
          <p>{finding.suggested_fix}</p>
        </>
      )}

      <h4>Verification</h4>
      <dl className="meta-grid">
        <dt>verdict</dt>
        <dd>{v ? v.final_verdict : finding.verdict}</dd>
        <dt>confidence</dt>
        <dd style={{ display: "flex", alignItems: "center" }}>
          <ConfidenceBar value={conf} />
        </dd>
        {v && (
          <>
            <dt>deterministic</dt>
            <dd>{v.passed_deterministic ? "passed" : "failed"}</dd>
            <dt>escalated to LLM</dt>
            <dd>{v.escalated ? "yes" : "no"}</dd>
            {v.llm_verified != null && (
              <>
                <dt>LLM verified</dt>
                <dd>{v.llm_verified ? "yes" : "no"}</dd>
              </>
            )}
          </>
        )}
      </dl>

      {v?.llm_reasoning && (
        <>
          <h4>Verifier reasoning</h4>
          <p className="small muted">{v.llm_reasoning}</p>
        </>
      )}

      {v?.deterministic_checks && (
        <>
          <h4>Deterministic checks</h4>
          <pre className="small">
            {JSON.stringify(v.deterministic_checks, null, 2)}
          </pre>
        </>
      )}

      <hr className="sep" />

      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div className="row" style={{ gap: 8 }}>
          <SeverityBadge severity={finding.severity} />
          <CategoryChip category={finding.category} />
        </div>
        {finding.github_url && (
          <a href={finding.github_url} target="_blank" rel="noreferrer">
            View on GitHub ↗
          </a>
        )}
      </div>

      <div style={{ marginTop: 14 }}>
        <JsonViewer data={finding} label="Raw finding JSON" />
      </div>

      <div className="feedback-row">
        <span className="faint small">Was this useful?</span>
        <button
          className="small"
          disabled={sent !== null}
          onClick={() => sendFeedback("helpful")}
        >
          👍 Helpful
        </button>
        <button
          className="small"
          disabled={sent !== null}
          onClick={() => sendFeedback("not_helpful")}
        >
          👎 Not helpful
        </button>
        <button
          className="small"
          disabled={sent !== null}
          onClick={() => sendFeedback("false_positive")}
        >
          🚫 False positive
        </button>
        {sent && <span className="thanks">recorded: {sent.replace(/_/g, " ")}</span>}
        {err && <span className="faint small">{err}</span>}
      </div>
    </div>
  );
}
