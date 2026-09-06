# AGENTS.md — Resume Notes for BuildGate

This file exists so a future session (human or agent) can pick this work back up
without re-deriving context. Read this before touching the code.

## What this is

BuildGate per `buildgate-phase-plan.md` and `buildgate-core-requirements.md`.
An AI governance layer that challenges management requests before engineering
capacity is committed, running entirely locally.

- **Phase 1 — complete, verified, committed** (`73fcb8b`).
- **Phase 2 — in progress, uncommitted.** Details below.

## Status as of 2026-09-06

### Phase 1 — done

Verified end to end: clean `docker compose down -v && up -d`, migrations, seed,
pytest, browser click-through. Three defects were found and fixed in `73fcb8b`
(migration enum double-create, mid-token chunk overlap, Windows separator
handling in filename sanitization). All Phase 1 exit criteria pass except the
Linux `host.docker.internal` path, which was verified by configuration
(`extra_hosts` is present) rather than on an actual Linux host.

### Phase 2 — in progress

**Backend suite: 37 passed.** Nothing below is committed yet.

Built and working:

- `app/schemas/agent.py` — the common agent output schema; also generates the
  JSON Schema passed to Ollama's `format`.
- `app/services/llm.py` — `LLMProvider` / `OllamaProvider`. Schema-constrained,
  `temperature=0`, fixed seed, **no fallback path by design**.
- `app/agents/` — `AgentSpec` + the `PRODUCT` reviewer. Per-agent retrieval
  query and a fixed finding taxonomy, so Phase 3's other six cannot collapse
  into paraphrases of each other. Prompt-injection rule and grounding rule are
  stated on every agent.
- `app/services/evidence.py` — evidence-ID validation. Strips IDs not in the
  agent's own retrieval set, demotes ungrounded significant findings to
  `evidence_status: MISSING`, keeps stripped IDs for audit.
- `app/services/review.py` — async run orchestration, per-agent state, retry,
  audit events (`REVIEW_STARTED`, `AGENT_REVIEW_COMPLETED`).
- `app/api/reviews.py` — `POST /api/requests/{id}/review` (202 + job record),
  `GET /api/reviews/{run_id}` (polling), `GET /api/requests/{id}/reviews`,
  `GET /api/requests/{id}/evidence/{evidence_id}` (resolves a reference to its
  source chunk text).
- `alembic/versions/0002_review_runs.py` — `review_runs` + `agent_runs`.
  Applied cleanly.
- Tests: `test_evidence_grounding.py` (7), `test_review_run.py` (9), plus a
  `FakeLLMProvider` in `conftest.py` so the suite never needs Ollama.

### Phase 2 — NOT built yet

1. **The decision engine.** This is the biggest remaining piece.
   `buildgate-decision-engine-spec.md` was **missing from the repo** and has
   been *derived* from `buildgate-core-requirements.md` — it is written and
   marked "pending review". **It has not been approved and no code implements
   it yet.** The wiring seam is `_finalize()` in `app/services/review.py`,
   which currently closes the run without computing a decision.
   Two things in that spec need a human answer:
   - the four numeric thresholds (`confidence_floor` etc.) were never specified
     anywhere and are proposed, not authoritative;
   - the stage-1/stage-2 ordering open question — whether an incomplete review
     that also contains a binding BLOCK should report REVISE (current, literal
     reading) or BLOCKED.
   Thresholds already live in `app/config.py`, so changing them is a config
   edit, not an engine edit.
2. **Accept / send for revision / override** (Feature 5) — none of it. Needs
   server-side enforcement that an override cannot be submitted with any field
   missing, plus `DECISION_*` audit events.
3. **All Phase 2 UI.** No frontend work has been done at all: no trigger
   button, no per-agent Pending/Running/Complete polling view, no decision
   screen, no click-to-resolve evidence, no audit reconstruction view. The API
   endpoints they need all exist.

## The open blocker: model latency and quality

This is the risk the phase plan flagged, and it has materialized. Measured on
this machine (CPU, no GPU), one `PRODUCT` call against the seeded demo request
(10 chunks, ~8.9k char prompt):

| Model | Latency | Result |
|---|---|---|
| `llama3.2:1b` | 157.6s | schema-valid, but poor quality — scored 85/PASS while emitting 9 findings that were the taxonomy echoed back, all with empty `evidence_ids` |
| `llama3` | >300s | timed out at the old `llm_timeout_seconds` default; a trivial prompt alone took 173s |

A benchmark of `llama3` against the full evidence prompt with a 1500s timeout
was still running when this session was paused — **its result is not known**.
Re-run it before deciding.

Consequences to weigh, per the phase plan's own guidance ("if one call takes 90
seconds, seven will take ten minutes, and that changes what Phase 3 can look
like"):

- `llm_model` currently defaults to `llama3` in `app/config.py`, which does not
  complete reliably here. This default is probably wrong and is unresolved.
- `llm_timeout_seconds` defaults to 300.0, which is below what `llama3` needs.
- Options not yet tried: a flatter output schema (the phase plan suggests
  this), passing fewer chunks, or a different model entirely.

**Do not start Phase 3 until this is settled.** Seven agents multiply it.

## Two findings worth not rediscovering

- **Ollama's `format` does not enforce numeric ranges.** It constrains JSON
  structure and types only. `llama3.2:1b` returned `"confidence": 100` for a
  field bounded 0.0–1.0. Pydantic validation after the call is the only thing
  enforcing ranges; `OUTPUT_RANGE_RULE` in `app/agents/base.py` states them in
  the prompt, which is what actually stopped it happening.
- **A retry at `temperature=0` with a fixed seed is a no-op.** It re-samples
  identically, so the mandated "one retry before marking the agent failed"
  would never change anything. `OllamaProvider.generate_json` offsets the seed
  by attempt number to fix this. See `docs/DECISIONS.md`.

## Environment notes (Windows host)

- Project lives at `E:\MTG\buildgate\buildgate`. Earlier notes referencing
  `C:\Users\<user>\Documents\MTG\buildgate`, `D:\Tai-Labs\buildgate`, or a
  `movin` user profile are stale.
- Docker CLI is on PATH. Ollama is at
  `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`. `make` is **not** installed —
  use the raw `docker compose` commands in `README.md`.
- Host port 5432 is taken by an unrelated project, so `.env` sets
  `POSTGRES_HOST_PORT=5433`. Containers still reach the DB as `db:5432`.
- **Disk is a hazard.** C: has run out mid-build before, which also wedged the
  Docker engine until Docker Desktop was restarted. The `api` image needs
  >10 GB of scratch for torch wheels on a cold build. `pip cache purge` and
  `npm cache clean --force` reclaimed ~13 GB last time.
- Ollama must bind `0.0.0.0:11434` to be reachable from the container; the
  default `127.0.0.1` bind is not. If it is down, ingestion silently falls back
  to sentence-transformers (visible in `GET /api/runtime`), but **review calls
  fail loudly by design**.

## Commands

```bash
docker compose up -d --build            # start / rebuild
docker compose exec api python -m app.scripts.seed_demo
docker compose exec -e DATABASE_URL=postgresql+psycopg://buildgate:buildgate@db:5432/buildgate_test api pytest -q
```

## Things worth knowing before changing code

- **The pytest suite does not exercise the Alembic migration.**
  `tests/conftest.py` builds the schema with `Base.metadata.create_all()`. A
  green run says nothing about migration correctness — that is exactly what let
  the Phase 1 migration bug survive. Test migrations by booting `api` against a
  fresh volume.
- **Any new postgres enum in a migration needs `create_type=False`**, or
  `op.create_table` re-emits `CREATE TYPE` after the explicit `create()` and the
  migration dies. `0002` follows this pattern; copy it.
- `db/init/01-create-test-db.sql` only runs on a *fresh* named volume. If
  `buildgate_test` is missing, `docker compose down -v` first.
- `NEXT_PUBLIC_API_BASE_URL` is baked in at Docker **build** time. Changing the
  API host/port needs a `web` rebuild, not a restart.
- Nothing prevents a corpus from mixing embedding providers: if Ollama is down
  for one ingestion and up for another, chunks land in different vector spaces
  at the same 768 dimensions and retrieval degrades silently. The provider used
  is recorded per document in the `DOCUMENT_INDEXED` audit payload.

## Next step on resume

1. Re-run the `llama3` full-evidence benchmark and settle the model / timeout /
   schema-shape question above. Nothing else in Phase 2 is blocked by it, but
   Phase 3 is.
2. Get the derived `buildgate-decision-engine-spec.md` reviewed, then implement
   `evaluate()` and its truth-table tests, and wire it into `_finalize()`.
3. Accept / revise / override + audit (Feature 5).
4. Phase 2 UI.

The working tree carries all of the above uncommitted. Consider committing the
working Phase 2 backend before continuing.
