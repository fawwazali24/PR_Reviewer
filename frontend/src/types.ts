// Types mirror the backend Pydantic schemas (backend/app/schemas/__init__.py).
// Kept deliberately close to the wire format so the raw JSON viewer and the
// typed views agree.

export type IndexingStatus =
  | "not_started"
  | "indexing"
  | "indexed"
  | "failed";

export type ReviewStatus = "queued" | "running" | "done" | "failed";

export type Severity = "info" | "low" | "medium" | "high" | "critical";

export type FindingCategory =
  | "business_logic"
  | "security"
  | "cross_file"
  | "maintainability"
  | "test_coverage";

export type VerificationVerdict = "verified" | "rejected" | "uncertain";

export type FeedbackVerdict = "helpful" | "not_helpful" | "false_positive";

export interface Repository {
  id: number;
  owner: string;
  name: string;
  full_name: string;
  url: string;
  default_branch: string | null;
  language: string;
  indexing_status: IndexingStatus;
  indexed_at: string | null;
  last_indexed_sha: string | null;
  indexing_error: string | null;
  created_at: string;
}

export interface PullRequest {
  number: number;
  title: string;
  author: string | null;
  state: string;
  html_url: string;
  head_sha: string;
  base_sha: string | null;
  updated_at: string | null;
  additions: number;
  deletions: number;
  changed_files: number;

  last_reviewed_sha: string | null;
  up_to_date: boolean;
  latest_review_id: number | null;
  latest_review_status: ReviewStatus | null;
}

export interface Verification {
  passed_deterministic: boolean;
  deterministic_checks: Record<string, unknown> | null;
  escalated: boolean;
  llm_verified: boolean | null;
  llm_reasoning: string | null;
  final_verdict: VerificationVerdict;
  adjusted_confidence: number | null;
}

export interface ReviewFinding {
  id: number;
  file: string;
  start_line: number;
  end_line: number;
  severity: Severity;
  category: FindingCategory;
  title: string;
  description: string;
  evidence: string | null;
  suggested_fix: string | null;
  confidence: number;
  verdict: VerificationVerdict;
  adjusted_confidence: number | null;
  github_url: string | null;
  verification: Verification | null;
}

export interface ChangedFile {
  filename: string;
  status: string;
  language: string | null;
  additions: number;
  deletions: number;
}

export interface ReviewStatusOut {
  id: number;
  status: ReviewStatus;
  stage: string | null;
  head_sha: string;
  finding_count: number;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

export interface ReviewDetail {
  id: number;
  pull_request_id: number;
  status: ReviewStatus;
  stage: string | null;
  head_sha: string;
  summary: string | null;
  error: string | null;
  finding_count: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  findings: ReviewFinding[];
  changed_files: ChangedFile[];
}

export interface ReviewTriggerResponse {
  review_id: number;
  status: ReviewStatus;
  message: string;
}

export interface Feedback {
  id: number;
  review_finding_id: number;
  verdict: FeedbackVerdict;
  comment: string | null;
  reviewer: string | null;
  created_at: string;
}
