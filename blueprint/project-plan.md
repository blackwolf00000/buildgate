# Project Plan

> Adopted from the existing BuildGate codebase and its source documents
> (`buildgate-core-requirements.md`, `buildgate-phase-plan.md`,
> `buildgate-decision-engine-spec.md`, `docs/DECISIONS.md`). Those documents
> remain the detailed authority; this plan summarizes them for the Blueprint
> workflow. Run `/overview` when it reads right.

## 1. Problem - What problem are we solving?

Management requests ("build this export button by the end of the quarter") get
committed to engineering before anyone checks them against the organization's
own policies, constraints, and history. BuildGate challenges a request *before*
engineering capacity is committed: specialist AI reviewers assess it against the
organization's own documents, policy code (not the model) computes a decision,
and a named human stays accountable for accepting or overriding it.

It runs entirely inside the customer's environment. Customer context never
leaves the machine.

Product rules (from the requirements):

1. Do not assume the request should be built. No-build is a valid recommendation.
2. Do not invent organizational evidence. Absent means absent.
3. AI recommends; humans are accountable and overrides are recorded.
4. Customer context stays local. No cloud fallback.
5. Evidence beats confident prose.
6. The final decision is policy-governed code, not model output.
7. BuildGate is not a chatbot. The artifact is an evidence-backed decision.

## 2. Users - Who is this for?

- **Manager / requester** - submits a structured request and attaches the
  supporting documents (product brief, security policy, engineering constraints,
  architecture notes, QA history).
- **Decision owner** - reads the board's findings and the computed decision,
  then accepts it, sends it back for revision, or overrides it with a recorded
  reason, risk owner, accepted risks, and approver name.

In v0.1 these are the same trusted operator, with no authentication and
`approved_by` as free text.

> TODO (confirm): the eventual target organization or buyer, if one is known.

## 3. Features - What does the MVP need?

The five MVP features, all built (v0.1 scope ends here):

- **Request intake with local evidence ingestion** - structured request with
  `deadline_is_fixed`; `.md`/`.txt` upload with safety controls; chunk, embed
  locally, store in pgvector; semantic evidence search.
- **Multi-agent specialist review** - seven reviewers (`PRODUCT`, `BA`,
  `ARCHITECTURE`, `ENGINEERING`, `QA`, `SECURITY`, `USER_EVIDENCE`), one local
  model, schema-constrained output, a fixed finding taxonomy per agent, async
  job with polling.
- **Evidence grounding** - every `evidence_id` validated in code against the
  chunks retrieved for that call; fabricated ids stripped; references open to
  the source text.
- **Deterministic decision engine** - pure `evaluate()`, strict rule order with
  a mandatory fallback, configurable thresholds, rule ids recorded.
- **Human accountability and audit trail** - accept / revise / override, with
  override fields enforced server-side; append-only audit events.

Still owed for the MVP's own exit criteria: a demo that reliably BLOCKs (with a
snapshot test), demo polish, and an honest demo timing.

Explicitly out of scope for v0.1: PDF/CSV uploads, authentication, multi-user
accounts, any cloud model.

> TODO (confirm): the **Privacy page** (deployment mode, runtime, endpoint,
> database, upload location, and a *measured* external-call count) is in the
> requirements and the Phase 3 exit criteria, but was not chosen for the
> roadmap during adoption. Add it to the build plan or record it as deferred in
> `docs/DECISIONS.md`.

## 4. Data - What are we storing?

All in local PostgreSQL 16 + pgvector, plus a local upload volume:

- **Requests** - required and optional intake fields, status (`DRAFT`,
  `READY_FOR_REVIEW`, `REVIEWING`, `APPROVED`, `REVISE`, `BLOCKED`,
  `OVERRIDDEN`).
- **Documents** - original and generated internal filename, extension, size,
  processing status and failure reason. Files live in the `buildgate_uploads`
  volume.
- **Chunks** - text, document and chunk index, 768-dimension embedding.
- **Review runs** - async job record per `review_run_id` with per-agent status.
- **Agent reviews** - one row per agent per run: score, status, confidence,
  findings with evidence ids and evidence status, questions, required actions,
  assumptions.
- **Decisions** - computed status, rule ids fired, `policy_version`,
  `model_name`, `review_run_id`, `review_complete`, and the human resolution.
- **Audit events** - append-only, with timestamp and actor. References and
  hashes are stored, never full prompts, documents, tokens, or secrets.

## 5. Tech - What stack are we using?

- **Frontend** - Next.js 14 (App Router), React 18, TypeScript (strict),
  Tailwind CSS 3. Client components talk to the API through `frontend/lib/api.ts`.
- **Backend** - Python 3.11, FastAPI, Pydantic 2 + pydantic-settings,
  SQLAlchemy 2, Alembic, psycopg 3, httpx.
- **Database** - PostgreSQL 16 with pgvector.
- **AI runtime** - Ollama on the host: `qwen2.5:3b` for review,
  `nomic-embed-text` for embeddings, sentence-transformers as the only (visible)
  embedding fallback.
- **Tests** - pytest in the `api` container against a separate `buildgate_test`
  database with a fake embedding provider.
- **Run** - Docker Compose (`db`, `api`, `web`). A separate single-container
  image (root `Dockerfile`, `start.sh`) targets Hugging Face Spaces.

## 6. Monetize - How will this make money?

Not applicable for v0.1, which is a demonstrable MVP.

> TODO (confirm): any intended commercial model.

## 7. UI/UX - How should this look and feel?

A plain, functional light UI in Tailwind's slate palette: a request list and
dashboard, a request form, and a request detail page that carries documents,
evidence search, the review board with per-agent progress, the decision panel
with rules fired, and the audit trail. Status and decision badges carry the
semantic colour. Evidence references expand inline to the exact source text.

The artifact is an evidence-backed decision, not a chat. A stranger should be
able to follow the full demo in about five minutes.

## 8. Deployment - Where and how will this ship?

- **Local (primary)** - `docker compose up -d --build`, Ollama on the host bound
  to `0.0.0.0:11434`. The API runs migrations on boot. Env vars by name are in
  `.env.example` (for example `DATABASE_URL`, `POSTGRES_HOST_PORT`, `LLM_MODEL`,
  `NEXT_PUBLIC_API_BASE_URL`). Health check: `GET /health`.
- **Hugging Face Spaces** - one container (Postgres + pgvector, Ollama with
  models baked in, FastAPI, Next.js on port 7860 rewriting `/api/*` to FastAPI).
  Storage is ephemeral, so the database is re-seeded on each cold start. Free
  Spaces are public while BuildGate has no authentication. See
  `HUGGINGFACE-DEPLOY.md`. The image has not yet been built or verified.

## 9. Usage model and constraints (optional)

- **Scale and users** - a demo / MVP v0.1 run by one trusted operator on one
  machine, or as a public demo Space with seeded data.
- **No authentication** by design for v0.1; `approved_by` is free text. This is
  a stated limitation, not an oversight.
- **Hard constraint: customer isolation.** All inference is local through
  Ollama, never a cloud model, including as a fallback. All outbound HTTP goes
  through one allowlisted wrapper with counted rejections. If Ollama is
  unreachable for review, fail loudly.
- **Untrusted input that is real:** uploaded documents (file safety, path
  traversal, and prompt injection inside document text, which agents must treat
  as evidence only).
- **Audit integrity:** audit events are append-only, decisions resolve once,
  and re-runs never overwrite prior rows.
- **Host constraint for local runs:** ~8 GB RAM and limited disk; model choice
  and concurrency are tuned to that, not assumed.
