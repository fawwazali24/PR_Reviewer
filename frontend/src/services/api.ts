// Thin fetch wrapper over the read-only backend. The dashboard itself performs
// no GitHub calls and never writes to GitHub — it only reads the backend, which
// is the single source of review data.
import type {
  ChangedFile,
  Feedback,
  FeedbackVerdict,
  PullRequest,
  Repository,
  ReviewDetail,
  ReviewFinding,
  ReviewStatusOut,
  ReviewTriggerResponse,
} from "../types";

const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ||
  "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (e) {
    throw new ApiError(0, `Network error reaching the API at ${API_BASE}. Is the backend running?`);
  }

  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      if (body && typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail)) detail = JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body — keep the status line */
    }
    throw new ApiError(resp.status, detail);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const api = {
  apiBase: API_BASE,

  // ---- repositories ----
  listRepositories: () => request<Repository[]>("/repositories"),

  getRepository: (id: number) => request<Repository>(`/repositories/${id}`),

  addRepository: (url: string) =>
    request<Repository>("/repositories", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  indexRepository: (id: number) =>
    request<{ repository_id: number; status: string }>(
      `/repositories/${id}/index`,
      { method: "POST" }
    ),

  listPulls: (id: number) => request<PullRequest[]>(`/repositories/${id}/pulls`),

  // ---- reviews ----
  triggerReview: (repository_id: number, pr_number: number, force = false) =>
    request<ReviewTriggerResponse>("/reviews/trigger", {
      method: "POST",
      body: JSON.stringify({ repository_id, pr_number, force }),
    }),

  reviewStatus: (reviewId: number) =>
    request<ReviewStatusOut>(`/reviews/${reviewId}/status`),

  reviewDetail: (reviewId: number) =>
    request<ReviewDetail>(`/reviews/${reviewId}`),

  // ---- findings ----
  getFinding: (findingId: number) =>
    request<ReviewFinding>(`/findings/${findingId}`),

  submitFeedback: (
    findingId: number,
    verdict: FeedbackVerdict,
    comment?: string
  ) =>
    request<Feedback>(`/findings/${findingId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ verdict, comment: comment ?? null }),
    }),
};

export type { ChangedFile };
