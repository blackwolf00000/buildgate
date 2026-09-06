# AGENTS.md — Resume Notes for BuildGate

This file exists so a future session (human or agent) can pick this work back up
without re-deriving context. Read this before touching the code.

## What this is

BuildGate per `buildgate-phase-plan.md` and `buildgate-core-requirements.md`.
An AI governance layer that challenges management requests before engineering
capacity is committed, running entirely locally.

- **Phase 1 — complete, verified, committed** (`73fcb8b`).
- **Phase 2 — decision engine done; Feature 5 and all UI outstanding.**
  Details below.

## Status as of 2026-09-06

### Phase 1 — done

Verified end to end: clean `docker compose down -v && up -d`, migrations, seed,
pytest, browser click-through. Three defects were found and fixed in `73fcb8b`
(migration enum double-create, mid-token chunk overlap, Windows separator
handling in filename sanitization). All Phase 1 exit criteria pass except the
Linux `host.docker.internal` path, which was verified by configuration
(`extra_hosts` is present) rather than on an actual Linux host.

### Phase 2 — in progress

**Backend suite: 73 passed.**

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
- `app/services/decision_engine.py` — `evaluate()`, pure, implementing every
  rule in `buildgate-decision-engine-spec.md`. Wired into `_finalize()` in
  `app/services/review.py`, which writes the `decisions` row and the
  `DECISION_CREATED` audit event. Verified end to end against a real model.
- Tests: `test_evidence_grounding.py`, `test_review_run.py`,
  `test_decision_engine.py` (all 18 truth-table rows, purity over 100 calls,
  config-driven thresholds), plus a `FakeLLMProvider` in `conftest.py` so the
  suite never needs Ollama.

### Phase 2 — NOT built yet

1. **Accept / send for revision / override** (Feature 5) — none of it. Needs
   server-side enforcement that an override cannot be submitted with any field
   missing, plus the `DECISION_ACCEPTED` / `REVISION_REQUESTED` /
   `DECISION_OVERRIDDEN` audit events. `DECISION_CREATED` is already written.
2. **All Phase 2 UI.** No frontend work has been done at all: no trigger
   button, no per-agent Pending/Running/Complete polling view, no decision
   screen, no click-to-resolve evidence, no audit reconstruction view. Every
   API endpoint they need already exists.

## The open blocker: the model, on this hardware

This is the risk the phase plan flagged, and it is real. **This machine has
7.4 GB of RAM**, and that is the binding constraint.

| Model | Result |
|---|---|
| `llama3` (8B, ~5 GB) | **Cannot load at all.** Ollama returns HTTP 500, `unable to allocate CPU buffer`. An earlier run that appeared to be a 300s timeout was really this. |
| `llama3.2:1b` (1.3 GB) | Loads and works. One full review call ≈ **295s** on the demo request. |

`llama3.2:1b` completes the pipeline but its *output quality* is poor. On the
seeded demo request it returned score 85 / `PASS` with 9 findings that were the
finding taxonomy echoed back, every one `INFO` severity with **zero evidence
citations** — so the decision engine correctly computed `APPROVED` via
`A1_ALL_CLEAR`.

That is a problem, because `buildgate-core-requirements.md` Feature 4 says the
demo request is "done when it reliably produces BLOCK". The engine is right;
the reviewer feeding it is not good enough. Two Phase 2 exit criteria are
effectively blocked on this:

- "every finding's evidence reference opens to real local text" — vacuous while
  the model cites nothing;
- the demo producing BLOCK.

`llm_model` still defaults to `llama3` in `app/config.py`, which **cannot run
here**. Local `.env` overrides it to `llama3.2:1b` with a 900s timeout. The
committed default was deliberately left alone because the model choice is a
human decision.

Options not yet tried, in rough order of promise: a mid-size quantized model
that fits in ~2-3 GB (`qwen2.5:3b`, `phi3:mini`, `gemma2:2b` — none installed,
each needs an `ollama pull`); a flatter output schema, which the phase plan
explicitly suggests; passing fewer chunks; or more RAM / a GPU.

**Do not start Phase 3 until this is settled.** Seven agents multiply both the
latency and the quality problem.

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

1. Settle the model question above — it gates the demo producing BLOCK, and it
   gates Phase 3 entirely.
2. Get `buildgate-decision-engine-spec.md` reviewed. It is **implemented and
   fully tested**, but the four numeric thresholds were derived rather than
   specified, and the stage-1/stage-2 ordering carries an open question. Both
   are cheap to change: thresholds are config, ordering is one block in
   `evaluate()`.
3. Accept / revise / override + the remaining audit events (Feature 5).
4. Phase 2 UI.
