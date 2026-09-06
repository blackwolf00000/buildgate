# AGENTS.md — Resume Notes for BuildGate

This file exists so a future session (human or agent) can pick this work
back up without re-deriving context. Read this before touching the code.

## What this is

BuildGate Phase 1 ("Foundation and evidence pipeline") per
`buildgate-phase-plan.md` and `buildgate-core-requirements.md`. No AI/LLM
involved in this phase — it's request intake, document upload, chunking,
local embedding, and semantic retrieval, with the full DB schema for later
phases already in place.

## Status as of 2026-09-06

**Phase 1 is code-complete AND verified end to end.** The verification that
previous sessions never finished has now been run in full: clean
`docker compose down -v && up -d`, migrations, seed, the pytest suite, and a
browser click-through. Three real defects were found and fixed (below).

Every Phase 1 exit criterion in `buildgate-phase-plan.md` now passes, except
that the Linux `host.docker.internal` path was verified by configuration
(`extra_hosts` is present on the `api` service) rather than by running on an
actual Linux host.

### Verified this session

- `web` (Next.js) image builds clean, TypeScript strict mode included.
- `api` image builds; cold `pip install` is ~20-25 min (torch).
- `alembic upgrade head` applies `0001_initial_schema.py` against real
  Postgres+pgvector — 6 tables + `alembic_version`, all 7 enums, `vector`
  extension.
- `db/init/01-create-test-db.sql` does create `buildgate_test` on a fresh
  volume.
- Seed ingests all 5 demo docs to `READY`, 10 chunks, all 768-dim.
- Evidence search for `data classification` returns the
  `security-policy.md` "Data classification" chunk as the top hit
  (score ~0.59).
- Backend suite: **21 passed**.
- UI click-through: dashboard, request detail, document list, evidence
  search, audit trail all render correctly.

### Defects found and fixed this session

1. **Migration crashed on every boot** —
   `0001_initial_schema.py` created each enum explicitly *and* let
   `op.create_table` re-emit `CREATE TYPE` (SQLAlchemy's `before_create`
   hook), giving `DuplicateObject: type "request_status" already exists`.
   Fixed by marking all 7 `postgresql.ENUM(...)` declarations
   `create_type=False`; the explicit `.create()`/`.drop()` calls ignore that
   flag, so both `upgrade()` and `downgrade()` still work.
2. **Chunk overlap started mid-token** — `chunk_text` picked a word boundary
   for the chunk *end* but computed the next start as raw `end - overlap`,
   so chunks began with fragments like `ok0530`. No content was lost, but it
   embedded meaningless fragments and failed
   `test_chunking_covers_the_whole_document`. The overlap start is now
   aligned to a word boundary too.
3. **`sanitize_original_filename` ignored Windows separators** — it called
   `os.path.basename` *before* replacing `\`, and on POSIX `basename` does
   not treat `\` as a separator, so `..\..\windows\system32\evil.txt` became
   `.._.._windows_system32_evil.txt`. Never a traversal risk (the stored
   name is always a generated UUID) but it failed
   `test_sanitize_strips_directory_components`. Separators are now
   normalized before the basename call.

### Non-code changes made this session

- `docker-compose.yml` now maps `"${POSTGRES_HOST_PORT:-5432}:5432"` for
  `db`. The committed default is unchanged; set `POSTGRES_HOST_PORT=5433` in
  `.env` when something else already holds host 5432. Containers always
  reach the DB as `db:5432`, so this is host-side only.
- `README.md` documents that override, and gives the raw `docker compose`
  equivalents of the `make` targets (`make` is not installed on Windows by
  default).

## Environment notes (Windows host)

- The project now lives at `E:\MTG\buildgate\buildgate`. It was previously
  under `C:\Users\<user>\Documents\MTG\buildgate` and, before that,
  `D:\Tai-Labs\buildgate`. Older notes referencing those paths, or a
  `movin` user profile, are stale.
- Docker CLI is on PATH (`C:\Program Files\Docker\Docker\resources\bin`).
  Ollama is at `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`.
- **Disk is the main hazard.** The `api` build needs well over 10 GB of
  scratch for torch wheels. A build already failed once with
  `No space left on device`, which also wedged the Docker engine (every API
  call returning 500 until Docker Desktop was restarted). Check free space
  before a cold rebuild. `pip cache purge` and `npm cache clean --force`
  reclaimed ~13 GB when this happened.
- Ollama must be reachable from inside the container at
  `host.docker.internal:11434`. A default `ollama serve` binds `127.0.0.1`,
  which containers cannot reach — it needs `OLLAMA_HOST=0.0.0.0:11434`.
  When Ollama is down, ingestion falls back to
  `sentence-transformers`/`all-mpnet-base-v2` and says so in
  `GET /api/runtime`; this is by design, not a failure.

## Repository map (Phase 1)

```
buildgate/
├── docker-compose.yml, .env.example, Makefile, README.md
├── docs/DECISIONS.md              — architectural rationale, read this too
├── db/init/01-create-test-db.sql  — creates buildgate_test on first volume init
├── data/demo/*.md                 — 5 seeded demo documents
├── backend/                       — FastAPI app, see app/main.py for routes
│   └── tests/                     — pytest suite
└── frontend/                      — Next.js App Router UI
```

## Things worth knowing before changing code

- **The pytest suite does not exercise the Alembic migration.**
  `tests/conftest.py` builds the schema with `Base.metadata.create_all()`.
  A green test run says nothing about migration correctness — that is what
  let defect #1 above survive. Test migrations by booting the `api`
  container against a fresh volume.
- `db/init/01-create-test-db.sql` only runs on a *fresh* named volume. If
  `buildgate_test` is missing, `docker compose down -v` first.
- `NEXT_PUBLIC_API_BASE_URL` is baked in at Docker **build** time, not
  container start (see `docs/DECISIONS.md`). Changing the API host/port
  needs a `web` image rebuild, not just a restart.
- Nothing prevents a corpus from mixing embedding providers: if Ollama is
  down during one ingestion and up during another, chunks land in different
  vector spaces at the same 768 dimensions, so retrieval degrades silently
  rather than erroring. The provider used is recorded per document in the
  `DOCUMENT_INDEXED` audit payload — check there if retrieval looks wrong.

## Next step

Phase 1 is done and verified. Nothing here is committed yet — the working
tree carries the three fixes plus the compose/README changes. Follow the
phase-boundary rule in `buildgate-phase-plan.md` (commit, then start
Phase 2 — the governance spine).
