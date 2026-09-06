# Architectural Decisions — Phase 1

## Schema created in full now

`agent_reviews` and `decisions` tables (and the `review_run_id`,
`policy_version`, `model_name` columns the spec calls out) are created in the
Phase 1 migration (`backend/alembic/versions/0001_initial_schema.py`) even
though nothing writes to them until Phase 2/4. Rationale: retrofitting these
fields later would touch every layer (models, migrations, schemas, API), per
the phase plan's explicit warning.

## Embedding provider fallback

`OllamaEmbeddingProvider` (model `nomic-embed-text`, 768 dims) is primary.
`SentenceTransformersEmbeddingProvider` (`all-mpnet-base-v2`, also 768 dims —
chosen specifically to match dimensions so the pgvector column width doesn't
need to vary by provider) is the local fallback if Ollama is unreachable at
the time the provider is first resolved. The active provider is cached for
the process lifetime (`app/services/embeddings.py`); restart the API
container to re-probe Ollama.

This fallback applies **only** to the embedding step. It does not weaken the
global "Ollama unreachable → fail loudly, no fallback" rule for LLM review
calls starting Phase 2 — those have no fallback path in the code at all, by
design. A fallback here is always visible via `GET /api/runtime`
(`embedding.active_provider`), never silent.

## Synchronous-looking upload, async processing

Document ingestion (extract → normalize → chunk → embed → store) runs via
FastAPI `BackgroundTasks`, not the job-record/polling pattern described for
Phase 2's multi-minute agent review runs. A few hundred milliseconds to a few
seconds of chunking+embedding for demo-sized `.md`/`.txt` files doesn't
justify that machinery yet; the frontend just polls `GET .../documents` every
2s while any document is `UPLOADED`/`PROCESSING`. The background task opens
its own DB session (`SessionLocal()`) rather than reusing the request-scoped
session, since the request's session may already be torn down by the time
the background task runs.

## Outbound HTTP counters are in-memory

`app/services/http_client.py` keeps allowed/rejected counts in a module-level
object. They reset when the API container restarts. This is called out
explicitly in the README as a known limitation for v0.1 rather than silently
presented as a lifetime total; persisting it is deferred until the Privacy
page (Phase 3) needs a durable number.

## NEXT_PUBLIC_API_BASE_URL is a build-time value

Next.js inlines `NEXT_PUBLIC_*` variables into the client bundle at `next
build` time, not at container start. `docker-compose.yml` passes it as a
Docker build arg (default `http://localhost:8000`) rather than a runtime
`environment:` entry, because a runtime-only value would never reach the
browser bundle. Since the browser always talks to the API through its
published host port (not the Docker-internal network), a build-time default
of `http://localhost:8000` is correct for the standard `docker compose up`
workflow without per-environment reconfiguration.

## Test database strategy

Tests run against a real Postgres + pgvector (`buildgate_test`, created by
`db/init/01-create-test-db.sql` on first volume init) rather than mocking the
database, because pgvector's vector type and cosine-distance operator aren't
available in SQLite. Table state is truncated after each test rather than
wrapped in a rolled-back transaction, because the ingestion background task
opens its own DB session/connection outside of any test-owned transaction —
truncation is what actually cleans up writes from both sessions. A fake,
deterministic `EmbeddingProvider` (`tests/conftest.py`) is injected via
`app.services.embeddings.set_embedding_provider()` so the suite never depends
on Ollama being reachable.

## Sync SQLAlchemy over async

FastAPI supports async handlers, but the ingestion pipeline, retrieval, and
this phase's request volume don't need it. Sync SQLAlchemy + `psycopg` v3
keeps the background-task session handling and pytest fixtures simpler; this
can be revisited if Phase 2's job-polling load makes it worthwhile.

---

# Architectural Decisions — Phase 2

## No fallback provider for review calls

`app/services/llm.py` has no fallback path at all, deliberately unlike
`app/services/embeddings.py`. A missing embedding degrades retrieval quality
and is recoverable; substituting anything for a *governance judgement* is not.
When Ollama is unreachable the call raises `LLMUnavailableError`, the agent is
marked `FAILED`, and the review is incomplete — which the decision engine's
completeness stage turns into "cannot APPROVE". This is the
"fail loudly, never degrade silently" rule from the customer-isolation
constraint.

## Retry offsets the seed

The requirements mandate `temperature = 0` and a fixed seed, and separately
mandate one retry before an agent is marked failed. Those two are in direct
tension: at temperature 0 with the same seed, a retry re-samples the identical
token stream, so it is a guaranteed no-op — the second attempt cannot succeed
where the first failed.

`OllamaProvider.generate_json` therefore offsets the seed by the attempt
number (`seed + attempt - 1`). The run stays fully reproducible — attempt N of
a given input is always identical — while a retry actually draws a different
sample. Without this the `llm_max_attempts` setting would be decorative.

## Schema-constrained generation does not constrain numeric ranges

Ollama's `format` parameter enforces JSON structure and types, not JSON Schema
`minimum`/`maximum`. Measured: `llama3.2:1b` returned `"confidence": 100` for a
field bounded 0.0–1.0. It is schema-shaped and still invalid.

Two consequences, both implemented. Pydantic validation after the call is not
belt-and-braces, it is the only thing enforcing ranges — hence
`AgentReviewOutput` carries the `ge`/`le` constraints. And `OUTPUT_RANGE_RULE`
states the ranges in the prompt, which is what stops the violation occurring
rather than merely catching it. Adding that rule moved `llama3.2:1b` from
`confidence: 100` to `confidence: 0.75` on the same input.

## Evidence validation is scoped to the agent's own retrieval set

`validate_findings()` checks each `evidence_id` against the chunks retrieved
for *that specific agent call*, not against every chunk in the request. A real,
resolvable ID that the agent was never shown is still stripped. The test
`test_agent_may_only_cite_chunks_it_was_shown` pins this: the question is not
"does this ID exist" but "was this agent actually shown it".

Stripped IDs are kept on the finding in `stripped_evidence_ids` rather than
discarded, so a fabrication is visible after the fact. A significant finding
(MEDIUM or above) left with no surviving evidence is demoted to
`evidence_status: MISSING`; INFO/LOW findings are allowed to stand uncited, so
that ordinary observations do not drown the real signal.

## Job records from the start, not retrofitted

`review_runs` + `agent_runs` exist even though Phase 2 ships a single agent and
could have returned synchronously. One measured `llama3` call against the demo
corpus exceeds five minutes; seven would hang any browser. Building the polling
pattern now is cheaper than retrofitting it in Phase 3, and the per-agent
`agent_runs` rows are what drive the Pending/Running/Complete UI.

`agent_runs` stores only error *class*, latency and attempt count — never
prompt text, document content, or model output, per the audit requirement to
log `request_id`, `agent_type`, status, latency, model and error class and
nothing sensitive.

## The model does not choose which agent it is

`run_agent` overwrites `raw["agent"]` with the spec's agent before validation,
and blanks `deadline_assessment` for every reviewer except `ENGINEERING`. The
schema makes both fields available to the model, so without this a reviewer
could mislabel itself or volunteer a deadline verdict outside its remit that
the decision engine would then read.

## num_ctx is pinned, not left to the model default

Ollama sizes the KV cache and compute buffers from the context window, and a
model's own default can be enormous — `qwen2.5` ships a 32k window. On a
memory-constrained host that allocation fails *before generation starts*, and
Ollama reports it as an opaque HTTP 500 (`failed to allocate buffer for kv
cache`, `failed to allocate compute pp buffers`).

This is genuinely counter-intuitive: on an 8 GB host, `qwen2.5:1.5b` (~0.99 GB
of weights) failed to load while `llama3.2:1b` (~1.32 GB) succeeded, purely
because of their differing default context windows. Model size on disk is not
what determines whether it fits.

`Settings.llm_num_ctx` (default 8192) is passed explicitly on every call. The
agent prompt is roughly 3.3k tokens, so 8192 leaves comfortable headroom.
Pinning it moved `qwen2.5:3b` from "will not load at all" to working in ~286s.

## Model selection is measured, not assumed

Measured on the seeded demo request, same prompt, same evidence, one PRODUCT
call each:

| Model | Latency | Findings | Grounded | Decision |
|---|---|---|---|---|
| `llama3.2:1b` | 295s | 9, all INFO | 0 | APPROVED |
| `qwen2.5:1.5b` | 244s | 5, all MEDIUM | 5 | REVISE |
| `qwen2.5:3b` | 286s | 3, all MEDIUM | 3 | REVISE |
| `llama3` (8B) | — | will not load; ~5 GB of weights exceeds available RAM |

Latency barely separates the three that run, so the choice is a quality one.
`llama3.2:1b` is unusable for this task: it echoed the finding taxonomy back as
nine INFO observations citing nothing, which the decision engine correctly but
uselessly turned into APPROVED. `qwen2.5:3b` grounds every finding, sets
`critical_information_missing` when the evidence genuinely does not answer the
question, and is what `.env` selects.

The committed default in `app/config.py` remains `llama3` and is *wrong for an
8 GB host*; it is left alone because the deployment-appropriate model is a
deployment decision, and `.env.example` documents the override.
