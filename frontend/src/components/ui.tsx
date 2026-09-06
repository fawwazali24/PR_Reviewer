// Small shared presentational helpers used across components.
import type { Severity } from "../types";

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`chip sev sev-${severity}`}>{severity}</span>;
}

export const SEV_CLASS: Record<Severity, string> = {
  critical: "crit",
  high: "hi",
  medium: "med",
  low: "lo",
  info: "inf",
};

export function CategoryChip({ category }: { category: string }) {
  return <span className="chip">{category.replace(/_/g, " ")}</span>;
}

export function shortSha(sha: string | null | undefined): string {
  return sha ? sha.slice(0, 7) : "—";
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function fmtDuration(
  startedAt: string | null | undefined,
  completedAt: string | null | undefined
): string {
  if (!startedAt || !completedAt) return "—";
  const started = new Date(startedAt).getTime();
  const completed = new Date(completedAt).getTime();
  if (!Number.isFinite(started) || !Number.isFinite(completed)) return "—";

  const seconds = Math.max(0, Math.round((completed - started) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <span className="row" style={{ gap: 8 }}>
      <span className="confidence-bar">
        <span style={{ width: `${pct}%` }} />
      </span>
      <span className="faint small mono">{pct}%</span>
    </span>
  );
}
