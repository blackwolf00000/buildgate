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
