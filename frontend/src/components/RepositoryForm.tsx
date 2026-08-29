import { useState } from "react";
import { api, ApiError } from "../services/api";
import type { Repository } from "../types";

// "Add repository" form. A repo enters the system ONLY here — there is no
// auto-discovery. The backend validates the read-only PAT can reach it before
// storing anything.
export default function RepositoryForm({
  onAdded,
}: {
  onAdded: (repo: Repository) => void;
}) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const value = url.trim();
    if (!value) return;
    setBusy(true);
    setErr(null);
    try {
      const repo = await api.addRepository(value);
      setUrl("");
      onAdded(repo);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit}>
      {err && <div className="error-banner">{err}</div>}
      <div className="form-row">
        <input
          type="text"
          placeholder="owner/repo or https://github.com/owner/repo"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={busy}
        />
        <button className="primary" type="submit" disabled={busy || !url.trim()}>
          {busy ? "Adding…" : "Add repository"}
        </button>
      </div>
    </form>
  );
}
