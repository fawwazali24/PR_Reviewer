import { useState } from "react";
import type { ReviewFinding } from "../types";
import { CategoryChip, SEV_CLASS, SeverityBadge, shortSha } from "./ui";
import FindingDetails from "./FindingDetails";

// The ranked list of surfaced findings. Each row expands to full detail.
export default function FindingList({ findings }: { findings: ReviewFinding[] }) {
  const [openId, setOpenId] = useState<number | null>(
    findings.length ? findings[0].id : null
  );

  if (findings.length === 0) {
    return (
      <div className="empty">
        No findings crossed the confidence threshold for this commit. That's a
        clean bill from the reviewer's value-add checks — not a guarantee of
        correctness.
      </div>
    );
  }

  return (
    <div>
      {findings.map((f) => {
        const open = openId === f.id;
        return (
          <div key={f.id} className={`finding ${SEV_CLASS[f.severity]}`}>
            <div
              className="finding-head"
              onClick={() => setOpenId(open ? null : f.id)}
            >
              <SeverityBadge severity={f.severity} />
              <div className="grow">
                <div className="f-title">{f.title}</div>
                <div className="f-loc">
                  {f.file}:{f.start_line}
                  {f.end_line !== f.start_line ? `-${f.end_line}` : ""}
                </div>
              </div>
              <CategoryChip category={f.category} />
              <span className="faint small">{open ? "▾" : "▸"}</span>
            </div>
            {open && <FindingDetails finding={f} />}
          </div>
        );
      })}
    </div>
  );
}

export function FindingListHeader({ headSha }: { headSha: string }) {
  return (
    <span className="faint small mono">reviewing @ {shortSha(headSha)}</span>
  );
}
