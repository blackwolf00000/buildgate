# BuildGate

An AI governance layer that challenges management requests before engineering
capacity is committed — running entirely inside the customer's environment.

This repository currently implements **Phase 1** of the build plan: request
intake, document upload, and local evidence retrieval. No AI review or
decision engine yet — see `buildgate-phase-plan.md` for the full roadmap.

## Prerequisites

- Docker Desktop (with Docker Compose v2)
- [Ollama](https://ollama.com) running on the host machine, with the
  embedding model pulled:
  ```bash
  ollama pull nomic-embed-text
  ```
  The backend talks to Ollama at `http://host.docker.internal:11434` by
  default (see `.env`). If Ollama isn't reachable, ingestion automatically
  falls back to a bundled local `sentence-transformers` model — this is
  reported (not hidden) via `GET /api/runtime`.

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

## Manual walkthrough

1. Open http://localhost:3000 and click **New Request**.
2. Fill in the required fields (title, description, business reason,
   requested deadline, and whether that deadline is fixed).
3. On the request detail page, upload one or more `.md`/`.txt` files. Status
   moves `PROCESSING` → `READY` as chunking + embedding complete
   (a couple of seconds for small files).
4. Use **Evidence search** to run a semantic query against the uploaded
   text and confirm it returns the right chunk with a similarity score.
5. Check the **Audit trail** section — `REQUEST_CREATED`, `DOCUMENT_UPLOADED`,
   and `DOCUMENT_INDEXED` events should all be present.

## Known limitations (Phase 1)

- No authentication — anyone who can reach the API can create/view requests.
- Only `.md` and `.txt` uploads are supported.
- No AI review, decision engine, or override flow yet (Phase 2).
- Outbound-HTTP counters (`GET /api/runtime`) reset when the API container
  restarts; they are not yet persisted.

See `docs/DECISIONS.md` for the architectural choices behind this phase.
