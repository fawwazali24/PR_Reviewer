import { useState } from "react";

// Collapsible raw-JSON view. The plan requires the exact machine-readable
// finding JSON be inspectable from the dashboard.
export default function JsonViewer({
  data,
  label = "Raw JSON",
}: {
  data: unknown;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = JSON.stringify(data, null, 2);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div>
      <div className="row" style={{ gap: 8 }}>
        <button className="ghost small" onClick={() => setOpen((o) => !o)}>
          {open ? "▾" : "▸"} {label}
        </button>
        {open && (
          <button className="ghost small" onClick={copy}>
            {copied ? "copied ✓" : "copy"}
          </button>
        )}
      </div>
      {open && <pre style={{ marginTop: 8 }}>{text}</pre>}
    </div>
  );
}
