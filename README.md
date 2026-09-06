# BuildGate

An AI governance layer that challenges management requests before engineering
capacity is committed — running entirely inside the customer's environment.

This repository implements **Phases 1 and 2** of the build plan: request
intake, document upload and local evidence retrieval; one grounded AI reviewer
(`PRODUCT`); a deterministic decision engine; and recorded human
accountability. The remaining six reviewers are Phase 3 — see
`buildgate-phase-plan.md` for the roadmap.

## Prerequisites

- Docker Desktop (with Docker Compose v2)
- [Ollama](https://ollama.com) running on the host machine, with both models
  pulled:
  ```bash
  ollama pull nomic-embed-text   # embeddings
  ollama pull qwen2.5:3b         # the reviewer
  ```
  Ollama must be reachable from inside Docker. Its default `127.0.0.1` bind is
  not, so start it with `OLLAMA_HOST=0.0.0.0:11434`.
  The backend talks to Ollama at `http://host.docker.internal:11434` by
  default (see `.env`). If Ollama isn't reachable, ingestion automatically
  falls back to a bundled local `sentence-transformers` model — this is
  reported (not hidden) via `GET /api/runtime`. **Review calls have no such
  fallback and fail loudly by design.**
- Roughly 8 GB of RAM. `qwen2.5:3b` is the default reviewer because it fits
  alongside the stack and grounds its findings; `llama3` (8B) needs ~5 GB of
  weights and will not load on an 8 GB host. Override with `LLM_MODEL` in
  `.env`. On CPU one review call takes about three to five minutes.

## Setup

```bash
cp .env.example .env
docker compose up --build
```

This starts three containers:

| Service | URL                   | Notes                                  |
|---------|-----------------------|-----------------------------------------|
| `web`   | http://localhost:3000 | Next.js UI                              |
| `api`   | http://localhost:8000 | FastAPI backend, runs migrations on boot|
| `db`    | localhost:5432        | Postgres 16 + pgvector                  |

If host port 5432 is already in use (another Postgres, for example), set
`POSTGRES_HOST_PORT=5433` in `.env` — only the host mapping changes, the
containers always reach the database as `db:5432`.

The `api` container runs `alembic upgrade head` automatically on startup, so
the schema is ready as soon as it's healthy.

### Seed the demo data

```bash
make seed
```

`make` is not installed by default on Windows. Without it, run the underlying
commands directly:

```bash
docker compose exec api python -m app.scripts.seed_demo
```

Creates a demo request ("Self-service customer data export button") and
ingests five seeded documents from `data/demo/` (product brief, security
policy, engineering constraints, architecture notes, QA history). Open
http://localhost:3000, click into the request, and try the evidence search
box with a query like `data classification`.

### Run the tests

```bash
make test
```

Or, without `make`:

```bash
docker compose exec -e DATABASE_URL=postgresql+psycopg://buildgate:buildgate@db:5432/buildgate_test api pytest -v
```

Runs the backend pytest suite (request validation, upload validation,
chunking, path traversal) against a separate `buildgate_test` database, with
a fake deterministic embedding provider so no Ollama call is required.

## How a review works

1. **Trigger.** `POST /api/requests/{id}/review` creates a job record and
   returns `202` immediately with a `review_run_id`. A single local model call
   takes minutes, so there is no synchronous path; the UI polls
   `GET /api/reviews/{run_id}`.
2. **Retrieve.** Each reviewer gets its own retrieval query. Below ~60 chunks
   the whole corpus is passed rather than running similarity search.
3. **Generate.** The prompt is constrained by a JSON Schema at the model call
   (`temperature 0`, fixed seed) and validated against Pydantic afterwards —
   Ollama's `format` enforces structure and types but **not** numeric ranges.
4. **Ground.** Every `evidence_id` the model emits is checked in code against
   the chunks actually retrieved for that call. Unresolvable ids are stripped
   and the finding is demoted to `evidence_status: MISSING`. A prompt
   instruction is not a control.
5. **Decide.** `evaluate()` computes the status from the structured agent
   output. It is a pure function — no clock, randomness, or database — and the
   model never selects the final status. See
   `buildgate-decision-engine-spec.md` for the rules, thresholds and truth
   table.
6. **Account.** The decision is a *recommendation*. The request stays
   `REVIEWING` until a named human accepts it, sends it back for revision, or
   overrides it.

A failed reviewer is recorded as failed; nothing is substituted for it, and a
review missing any expected agent can never produce `APPROVED`.

### Override

An override is impossible to submit without a reason, a risk owner, explicitly
ticked accepted risks, and an approver name. This is enforced server-side (in
both the request schema and the service layer), not merely disabled in the
form — blank counts as missing. A decision resolves once; a second accept or
override returns `409`. Re-running a review allocates a new `review_run_id` and
inserts a new `decisions` row, never overwriting the previous one.

## Manual walkthrough

1. Open http://localhost:3000 and click **New Request**.
2. Fill in the required fields (title, description, business reason,
   requested deadline, and whether that deadline is fixed).
3. On the request detail page, upload one or more `.md`/`.txt` files. Status
   moves `PROCESSING` → `READY` as chunking + embedding complete
   (a couple of seconds for small files).
4. Use **Evidence search** to run a semantic query against the uploaded
   text and confirm it returns the right chunk with a similarity score.
5. Press **Run review** under *Review board*. The `PRODUCT` reviewer moves
   `PENDING` → `RUNNING` → `COMPLETE` (three to five minutes on CPU).
6. Read the findings. Click any evidence reference to expand the exact local
   text behind it. A finding that cited nothing resolvable is badged
   *evidence missing*.
7. Under *Decision*, see the computed status and every rule that fired, with
   the deciding rule marked. Enter your name and accept, send for revision, or
   override.
8. Check the **Audit trail** — `REQUEST_CREATED`, `DOCUMENT_UPLOADED`,
   `DOCUMENT_INDEXED`, `REVIEW_STARTED`, `AGENT_REVIEW_COMPLETED`,
   `DECISION_CREATED` and your decision action should all be present.

## Known limitations

- No authentication — anyone who can reach the API can create/view requests.
- Only `.md` and `.txt` uploads are supported.
- Only the `PRODUCT` reviewer is implemented; the other six are Phase 3.
- Outbound-HTTP counters (`GET /api/runtime`) reset when the API container
  restarts; they are not yet persisted.

See `docs/DECISIONS.md` for the architectural choices behind this phase.
