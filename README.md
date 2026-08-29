# AI Powered PR Reviewer

A read-only assistant that reviews GitHub pull requests the way a senior engineer
would — surfacing the classes of issues that CI, linters, and static analysis
**don't** catch:

- **Intent vs. implementation gaps** — does the diff actually do what the PR says?
- **Business-logic / domain errors** — off-by-one in a billing rule, a wrong
  comparison in an authorization check, a broken invariant.
- **Context-dependent security** — a missing check that only matters given how
  the surrounding code is used.
- **Cross-file inconsistencies** — a change here that quietly breaks an assumption
  there.
- **Missing test coverage** — new branches or edge cases the PR leaves untested.

Every result lands on a dashboard, phrased as a **reviewer's open question**, with
the concrete evidence behind it and a working deep-link to the exact lines on
GitHub. It is deliberately tuned for **precision over recall** — a short list you
can trust beats a long list you learn to ignore.

---

## Non-negotiable constraints

These are baked into the architecture, not toggles:

| Constraint | How it's enforced |
| --- | --- |
| **Read-only** | Uses a fine-grained PAT with *read* scopes only. The GitHub client issues `GET` requests exclusively — there is no write code path. |
| **Never writes to GitHub** | No PR comments, no checks, no status, no commits. The **only** output is this dashboard's database. |
| **On-demand** | Reviews run only when you click *Review*. No scheduler, no polling loop. |
| **No duplicate work** | A commit already reviewed (`last_reviewed_sha == head_sha`) won't be re-reviewed unless you force it. |
| **Semgrep is corroboration, not a source** | Static-analysis hits are used as *evidence* to raise confidence — never surfaced as their own findings. |
| **Deterministic-first verification** | Cheap mechanical checks reject bad findings before any second LLM call is spent. |

---

## How a review works

```
click "Review" (dashboard)
        │
        ▼
POST /reviews/trigger ──► guard: skip if head_sha already reviewed
        │
        ▼  (FastAPI background task)
┌─────────────────────────────────────────────────────────────┐
│ 1. Fetch PR diff + head-commit sources (read-only)            │
│ 2. Parse diff → exact head-commit line ranges (unidiff)       │
│    + Tree-sitter enclosing symbols for changed lines          │
│ 3. Semgrep over head sources (corroborating evidence)         │
│ 4. RAG: retrieve domain context from the indexed repo         │
│    (function/class chunks; up-weights tests + validation code)│
│ 5. ONE main LLM review call (Gemini) → structured findings    │
│ 6. Verify each finding:                                       │
│      deterministic checks → reject if not attributable        │
│      semantic LLM re-check only when needed (skeptic pass)    │
│ 7. Apply confidence threshold → persist surfaced findings     │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
dashboard polls status → shows summary, ranked findings, evidence, GitHub links
```

---

## Stack

- **Backend** — FastAPI + SQLAlchemy 2.0 (sync), PostgreSQL + **pgvector**, Alembic.
- **LLM** — Google **Gemini** via `google-genai` (structured JSON output).
  `gemini-2.5-pro` for the review, `gemini-2.5-flash` for verification.
- **Embeddings** — **local** `sentence-transformers/all-MiniLM-L6-v2` (384-dim).
  No embedding API key, no data leaves the box for indexing.
- **Analysis** — `unidiff` (diff line-mapping), **Tree-sitter** (Python symbols),
  **Semgrep** (corroboration).
- **Frontend** — React + TypeScript + Vite (read-only dashboard).
- **Orchestration** — Docker Compose.

> **MVP scope:** Python repositories only.

---

## Prerequisites

1. **A GitHub fine-grained personal access token (read-only).**
   Grant it, for the repositories you want to review, *read-only* access to:
   - **Contents** — Read
   - **Pull requests** — Read
   - **Metadata** — Read (mandatory)

   Do **not** grant any write permission. The tool never needs one.

2. **A Google Gemini API key** — from Google AI Studio.

3. **Docker + Docker Compose** (recommended path).

---

## Quick start (Docker)

```bash
cp .env.example .env
```

Edit `.env` and set at least:

```
GITHUB_TOKEN=github_pat_...      # read-only fine-grained PAT
GEMINI_API_KEY=...               # Google AI Studio key
```

Then bring up the whole stack (Postgres+pgvector, API, dashboard):

```bash
docker compose up --build
```

- Dashboard → http://localhost:5173
- API docs → http://localhost:8000/docs

On first run the API applies migrations automatically, and the backend downloads
the local embedding model once (cached in a volume).

### Using it

1. **Add a repository** — paste `owner/repo` or a full GitHub URL. The token's
   read access is validated before anything is stored.
2. *(Recommended)* **Index** the repo — builds the RAG context that lets the
   reviewer reason about your domain. Reviews still run without it, just with
   less context.
3. **Pick a PR** from the live open-PR list and click **Review**.
4. **Watch it run** — the review page shows live stage progress, then the
   summary, the ranked findings (with evidence, verification trail, raw JSON),
   and deep-links to the exact lines on GitHub.

---

## Configuration (`.env`)

| Variable | Default | Notes |
| --- | --- | --- |
| `GITHUB_TOKEN` | — | Read-only fine-grained PAT. |
| `GITHUB_API_BASE` | `https://api.github.com` | Change for GitHub Enterprise. |
| `GEMINI_API_KEY` | — | Required for reviews to run. |
| `GEMINI_MODEL` | `gemini-2.5-pro` | Main review model. |
| `GEMINI_VERIFY_MODEL` | `gemini-2.5-flash` | Cheap verification model. |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Local, no API key. |
| `EMBEDDING_DIM` | `384` | Must match the model. |
| `DATABASE_URL` | `postgresql+psycopg2://prr:prr@db:5432/prr` | Compose overrides the host. |
| `RETRIEVAL_TOP_K` | `8` | Chunks pulled into review context. |
| `CONFIDENCE_THRESHOLD` | `0.55` | The precision/recall knob. Raise for fewer, stronger findings. |
| `CORS_ORIGINS` | `http://localhost:5173` | Dashboard origin. |

---

## Project layout

```
PR_reviewer/
├── docker-compose.yml          # db (pgvector) + api + web
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/                # migrations (baseline from models)
│   └── app/
│       ├── main.py             # FastAPI app + routers
│       ├── config.py           # settings (pydantic-settings)
│       ├── database.py         # sync engine / session
│       ├── enums.py
│       ├── models/             # SQLAlchemy models
│       ├── schemas/            # API request/response schemas
│       ├── api/                # repositories, reviews, findings, health
│       ├── github/             # read-only GitHub client + PR helpers
│       ├── analysis/           # diff parser, tree-sitter, semgrep
│       ├── rag/                # chunker, embeddings, vector store, retriever
│       ├── llm/                # prompts, client, reviewer, schemas
│       ├── verification/       # deterministic evidence, verifier, confidence
│       ├── indexing.py         # repo indexing background task
│       └── pipeline.py         # the on-demand review pipeline
│   └── tests/                  # pure-logic unit tests
└── frontend/                   # React + TypeScript + Vite dashboard
    └── src/
        ├── services/api.ts     # typed client for the backend
        ├── pages/              # Dashboard, Review
        └── components/         # RepositoryForm/List, PullRequestList,
                                # ReviewSummary, FindingList, FindingDetails,
                                # JsonViewer
```

---

## API surface

All read-only from GitHub's perspective. The dashboard uses these:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/repositories` | Register a repo (validates PAT read access). |
| `GET` | `/repositories` | List registered repos. |
| `GET` | `/repositories/{id}` | One repo. |
| `POST` | `/repositories/{id}/index` | Build/refresh the RAG index (background). |
| `GET` | `/repositories/{id}/pulls` | Live open PRs + local review state. |
| `POST` | `/reviews/trigger` | Queue a review (guards duplicate commits). |
| `GET` | `/reviews/{id}/status` | Lightweight status poll. |
| `GET` | `/reviews/{id}` | Full review: summary + surfaced findings. |
| `GET` | `/findings/{id}` | One finding. |
| `POST` | `/findings/{id}/feedback` | Record `helpful` / `not_helpful` / `false_positive`. |
| `GET` | `/health` | Liveness. |

---

## Local development (without Docker)

**Backend** — needs a running Postgres with the `vector` extension:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://prr:prr@localhost:5432/prr
alembic upgrade head
uvicorn app.main:app --reload
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

**Backend unit tests** (pure logic — diff mapping, symbols, chunking, verification):

```bash
cd backend
python -m pytest
```

---

## Design notes

- **The diff line-mapping is load-bearing.** Every finding and every GitHub
  deep-link anchors to *head-commit* line numbers derived from the PR's patch,
  so that mapping is exact and unit-tested.
- **Verification is two-tier by design.** Deterministic checks (is this line
  actually in the diff? does the symbol exist?) reject hallucinated or
  misattributed findings for free; only genuinely semantic claims spend a second
  LLM call, whose main job is catching *"the codebase already handles this."*
- **Confidence threshold is the tuning knob.** It's a single setting meant to be
  calibrated against a labeled fixture set to hit the precision the tool promises.
