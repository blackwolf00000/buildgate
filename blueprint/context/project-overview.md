# BuildGate - Project Overview

<!-- blueprint:source-hash a1308d5833cf532455d487d4bcf1a6d8b0c44621dced07381b0c09c878a04d3b -->

> An AI governance layer that challenges management requests before engineering capacity is committed, running entirely inside the customer's environment.

## Problem

Management requests get committed to engineering before anyone checks them against the organization's own policies, constraints, and history. BuildGate reviews a request first: seven specialist local AI reviewers assess it against the organization's documents, policy code (never the model) computes APPROVE / REVISE / BLOCK, and a named human stays accountable for the outcome.

Product rules: no-build is a valid outcome; absent evidence stays absent; AI recommends, humans decide; customer context stays local; evidence beats confident prose; the final decision is policy code; the artifact is a decision, not a chat.

## Users

- **Manager / requester** - submits a structured request and attaches supporting documents.
- **Decision owner** - reads findings and the computed decision, then accepts, sends for revision, or overrides with recorded accountability.

In v0.1 both are one trusted operator. No authentication; `approved_by` is free text.

## Usage model

- Demo / MVP v0.1: one trusted operator on one machine, or a public demo Space with seeded data.
- No authentication by design for v0.1 (a stated limitation).
- **Customer isolation is a hard constraint:** all inference is local via Ollama, never a cloud model, including as fallback. All outbound HTTP goes through one allowlisted wrapper with counted rejections. Review fails loudly if Ollama is unreachable.
- **Untrusted input:** uploaded documents (file safety, path traversal, prompt injection in document text, which agents treat as evidence only).
- **Audit integrity:** append-only audit events, decisions resolve once (second action returns 409), re-runs never overwrite prior rows.
- Local host is ~8 GB RAM with limited disk; model choice and concurrency are tuned to that.
- Out of scope for v0.1: PDF/CSV uploads, authentication, multi-user accounts, any cloud model.

## Features

Build-plan order. 1-17 are shipped; 18-22 are the roadmap. **Headline: the seven-agent review feeding the deterministic decision engine.**

1. **Stack foundation** - Compose stack, `/health`, `/api/runtime`, full schema via Alembic.
2. **Request intake** - create, list, reopen validated requests including `deadline_is_fixed`.
3. **Safe document upload** - `.md`/`.txt`, size cap, sanitized and generated names, no path traversal.
4. **Local ingestion pipeline** - extract, normalize, chunk (~1000/150), embed locally, pgvector; `PROCESSING_FAILED` without failing the request.
5. **Evidence retrieval and search** - per-query retrieval with small-corpus bypass (<~60 chunks), evidence search UI.
6. **Outbound HTTP wrapper** - allowlist plus allowed/rejected counters.
7. **Seeded demo data** - demo request and five documents in `data/demo/`.
8. **Async review runs** - `202` trigger, polling, per-agent progress, orphan recovery.
9. **PRODUCT reviewer end to end** - schema-constrained Ollama call, Pydantic validation, temp 0, seed offset per retry.
10. **Evidence grounding** - code-validated `evidence_id`s, fabricated ids stripped, finding demoted to `MISSING`.
11. **Deterministic decision engine** - pure `evaluate()`, ordered rules with fallback, configurable thresholds.
12. **Human accountability** - accept / revise / override, override fields enforced server-side.
13. **Audit trail** - append-only events and a history view.
14. **Review, decision, and evidence UI** - board, decision panel with rules fired, inline evidence.
15. **Six remaining reviewers** - schema-enforced taxonomies, distinct retrieval queries.
16. **Review latency tuning** - batched retrieval, keep_alive/release, chunk cap, pinned `num_ctx`, optional concurrency.
17. **Single-container Hugging Face image** - authored, not yet built.
18. **Reliable demo BLOCK** - seeded scenario BLOCKs via `B2` (SECURITY CRITICAL citing `security-policy.md`) across repeated runs, or record why not.
19. **Demo snapshot test** - `tests/fixtures/demo_run.json` plus a test locking the outcome.
20. **Demo polish and README refresh** - loading/error states, consistent badges, seven-agent walkthrough, honest limitations.
21. **Verify the Hugging Face image** - build, boot, seed, review, decide end to end.
22. **Demo timing** - full demo under five minutes, or a revised target with measured numbers.

## Data model

PostgreSQL 16 + pgvector. All ids are UUIDv4. Child rows cascade on request delete. Shapes below are shipped; roadmap features must not break them without a migration.

### Request
- `title` (str 300), `description`, `business_reason` (text), `requested_deadline` (date), `deadline_is_fixed` (bool) - required
- `requester`, `department` (str 200), `expected_outcome`, `target_users`, `notes` (text), `priority` (str 50) - optional
- `status` (`DRAFT|READY_FOR_REVIEW|REVIEWING|APPROVED|REVISE|BLOCKED|OVERRIDDEN`), `created_at`, `updated_at`
- has many Document, AuditEvent, ReviewRun, AgentReview, Decision

### Document
- `request_id` FK, `original_filename` (str 500), `stored_filename` (generated, str 200), `extension`, `size_bytes`
- `status` (`UPLOADED|PROCESSING|READY|PROCESSING_FAILED`), `failure_reason`
- has many DocumentChunk; file lives in the `buildgate_uploads` volume

### DocumentChunk
- `document_id` FK, `request_id` FK, `chunk_index` (int), `content` (text), `embedding` (vector 768)
- Evidence id format: `DOC-{document_id}-CHUNK-{chunk_index}`

### ReviewRun / AgentRun
- ReviewRun: `request_id` FK, `status`, `model_name`, `policy_version`, `error`, `completed_at`
- AgentRun: `review_run_id` FK, `agent`, `state`, `error_class`, `latency_ms`, `attempts`

### AgentReview
- `review_run_id`, `request_id` FK, `agent` (`PRODUCT|BA|ARCHITECTURE|ENGINEERING|QA|SECURITY|USER_EVIDENCE`)
- `score` (0-100), `status` (`PASS|WARNING|FAIL|BLOCK`), `confidence` (0.00-1.00), `summary`
- `findings` (JSONB: severity `INFO..CRITICAL`, category enum per agent, title, description, evidence_ids, evidence_status)
- `questions`, `required_actions`, `assumptions` (JSONB), `critical_information_missing` (bool), `deadline_assessment` (`FEASIBLE|DOUBTFUL|INFEASIBLE|UNKNOWN`, ENGINEERING only)

### Decision
- `review_run_id`, `request_id` FK, `status`, `policy_version`, `model_name`, `review_complete`, `rule_ids` (JSONB)
- Resolution: `accepted_at/by`, `overridden_at`, `override_reason`, `override_risk_owner`, `override_accepted_risks` (JSONB), `override_approver_name`

### AuditEvent
- `request_id` FK, `event_type` (`REQUEST_CREATED`, `DOCUMENT_UPLOADED`, `DOCUMENT_INDEXED`, `REVIEW_STARTED`, `AGENT_REVIEW_COMPLETED`, `DECISION_CREATED`, `DECISION_ACCEPTED`, `REVISION_REQUESTED`, `DECISION_OVERRIDDEN`), `actor`, `payload` (JSONB, references and hashes only), `created_at`. Append-only.

## Tech stack

- **Next.js 14 + React 18 + TypeScript strict + Tailwind 3** - UI; client components via `frontend/lib/api.ts`.
- **FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, psycopg 3, httpx** - API and services (Python 3.11).
- **PostgreSQL 16 + pgvector** - all persisted data and embeddings.
- **Ollama** - `qwen2.5:3b` review, `nomic-embed-text` embeddings; sentence-transformers is the only (visible) embedding fallback.
- **pytest** - backend suite in the `api` container against `buildgate_test`, fake providers, no Ollama.
- **Docker Compose** - `db`, `api`, `web`; root `Dockerfile` + `start.sh` for HF Spaces.

## Monetization

Not applicable for v0.1.

## UI/UX

Plain, functional light UI in Tailwind slate; semantic colour on status and decision badges; evidence references expand inline to the exact source text.

- `/` - dashboard
- `/requests` - request list
- `/requests/new` - request form
- `/requests/[id]` - documents, evidence search, review board with per-agent progress, decision panel with rules fired and actions, audit trail

API: `/health`, `/api/runtime`, `/api/requests` (CRUD, `/{id}/audit`, `/{id}/documents`, `/{id}/evidence-search`, `/{id}/review`, `/{id}/reviews`, `/{id}/decisions`), `/api/reviews/{run_id}`, `/api/decisions/{id}` (`/accept`, `/revision`, `/override`).

Target: a stranger follows the full demo in about five minutes.

## Deployment

- **Local (primary):** `docker compose up -d --build`, Ollama on host bound to `0.0.0.0:11434`. API migrates on boot. Env vars in `.env.example` (`DATABASE_URL`, `POSTGRES_HOST_PORT`, `LLM_MODEL`, `NEXT_PUBLIC_API_BASE_URL`, ...). Health: `GET /health`.
- **Hugging Face Spaces:** one container (Postgres + pgvector, Ollama with baked models, FastAPI, Next.js on 7860 rewriting `/api/*`). Ephemeral storage, re-seeded each cold start; public while unauthenticated. Unverified (feature 21). See `HUGGINGFACE-DEPLOY.md`.

## Open questions

> - **Privacy page:** required by the core requirements and Phase 3 exit criteria, but absent from the build plan. Add it as a feature or record it as deferred.
> - **Target buyer / organization** and any **commercial model**: unknown.
> - **Component library:** none in use; confirm that stays the case for feature 20.
> - **Decision-engine questions** (thresholds invented, `C1` stage, `UNKNOWN` deadline, confidence vs APPROVE, positive findings) live in `AGENTS.md` and the engine spec, not the plans; they may affect features 18-19.
