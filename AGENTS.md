# AGENTS.md — Resume Notes for BuildGate

This file exists so a future session (human or agent) can pick this work back up
without re-deriving context. Read this before touching the code.

## What this is

BuildGate, per `buildgate-core-requirements.md` (what to build) and
`buildgate-phase-plan.md` (the order to build it in). An AI governance layer
that challenges management requests before engineering capacity is committed,
running entirely on the customer's own machine.

**Phases 1 and 2 are complete, verified, and committed. Phase 3 has not
started.** Working tree is clean at `2b8df9e`.

| Phase | State |
|---|---|
| 1 — Foundation and evidence pipeline | done, exit criteria ticked |
| 2 — Governance spine (one reviewer) | done, exit criteria ticked, boundary rule satisfied |
| 3 — Full review board (seven reviewers) | **not started** |
| 4+ | not started |

`docker compose up -d --build` gives a working product: create a request, upload
documents, run a grounded review, get a policy-computed decision, accept or
override it with a named human on the record.

**Backend suite: 93 passed.**

## How it fits together

Read `docs/DECISIONS.md` alongside this — it holds the *why* for everything
below, and there is a lot of it.

```
request + documents
  -> chunk -> embed (nomic-embed-text) -> pgvector
  -> per-agent retrieval query  (app/agents/*.py: AgentSpec)
  -> schema-constrained model call, temp 0, fixed seed  (app/services/llm.py)
  -> evidence_id validation, fabricated ids stripped    (app/services/evidence.py)
  -> agent_reviews row                                  (app/services/review.py)
  -> evaluate(), pure policy code                       (app/services/decision_engine.py)
  -> decisions row + DECISION_CREATED
  -> a named human accepts / revises / overrides        (app/services/decisions.py)
```

Load-bearing points that are easy to break:

- **The model never picks the final status.** `evaluate()` does, from structured
  agent output. It is pure: no clock, randomness, DB, network, or logging.
- **Evidence grounding is a code control, not a prompt instruction.** Every
  `evidence_id` is checked against the chunks retrieved *for that specific agent
  call*. A real id the agent was never shown is still stripped.
- **A failed agent is recorded as failed.** Nothing is substituted, and a review
  missing any expected agent can never produce APPROVED.
- **Review calls have no fallback.** Ollama unreachable means the agent fails
  loudly. (Embeddings *do* fall back to sentence-transformers — a deliberate,
  visible exception, reported via `GET /api/runtime`.)
- **The decision is a recommendation.** `_finalize()` leaves the request in
  `REVIEWING`; only a human action moves its status.

Runs are asynchronous end to end: `POST .../review` returns 202 with a job
record, and the UI polls. There is no synchronous path.

## Phase 3 — what to do next

Goal per the phase plan: all seven reviewers returning schema-valid output, each
producing *materially different* findings, with the seeded scenario producing
BLOCK across repeated runs.

`app/agents/__init__.py` is the single place the registry changes. Adding an
agent is: a new `AgentSpec` (role, retrieval query, finding taxonomy, scoring
guidance) in `app/agents/<name>.py`, registered in `AGENT_REGISTRY`.
`EXPECTED_AGENTS` derives from it, and the decision engine's completeness stage
picks it up automatically. The remaining six are `BA`, `ARCHITECTURE`,
`ENGINEERING`, `QA`, `SECURITY`, `USER_EVIDENCE`.

`ENGINEERING` is the only agent whose `deadline_assessment` the engine reads;
`run_agent` blanks that field for every other reviewer, so the engine's
`B3`/`R5`/`R6` deadline rules only fire once that agent exists.

### Do these two things before cloning the pattern six times

1. **Fix the PRODUCT prompt.** Findings currently come back titled with the bare
   category name (`SCOPE_AMBIGUITY - The boundaries of what is being asked...`),
   and the model raises roughly one finding per category, which reads
   mechanically. The Phase 3 exit criterion *"a reader can identify which agent
   wrote a finding without the label"* is exactly what this style would fail.
   The taxonomy should steer the finding, not become its title. Fixing it once
   is far cheaper than fixing it in seven prompts.
2. **Decide what to do about latency.** One agent call is roughly 4–5 minutes on
   this hardware. Seven sequential is ~30 minutes per review, which is not a
   demo. The phase plan says explicitly to weigh this before multiplying.
   Options: run agents concurrently (they are independent — but they contend for
   the same single-model Ollama process, so measure before assuming a speedup),
   cut the board for the demo, shrink the prompt, or accept a long run and lean
   on the polling UI.

## Open question needing a human answer

`buildgate-decision-engine-spec.md` was **referenced by the requirements but
absent from the repository**. It has been *derived* from
`buildgate-core-requirements.md` Feature 4, and it is fully implemented and
tested — but it is still marked "pending review" and two things in it were never
specified by anyone:

- **The four numeric thresholds** (`confidence_floor` 0.60,
  `warning_revise_threshold` 3, `approve_min_average_score` 75,
  `approve_min_agent_score` 60). These are proposals. They live in
  `app/config.py`, so changing them is a config edit, not an engine edit.
- **Stage ordering.** Completeness is evaluated before BLOCK, which is the
  literal reading of the requirements. It means an incomplete review that *also*
  contains a binding BLOCK reports REVISE rather than BLOCKED. The blocker is
  still recorded in `rule_ids` and rendered in the UI, so nothing is lost — but
  if a binding BLOCK should outrank incompleteness, swap the two blocks in
  `evaluate()` and update truth-table row 18.

One derived choice worth understanding before touching it: score minimums are
APPROVE *preconditions*, not REVISE triggers. That is what keeps the mandatory
fallback reachable — the requirements name "no blocker, no fail, two warnings,
average 65" as a case that must match no rule, and a low-average REVISE trigger
would have swallowed it.

## Findings worth not rediscovering

- **Ollama's `format` does not enforce numeric ranges.** It constrains JSON
  structure and types only — `llama3.2:1b` returned `"confidence": 100` for a
  field bounded 0.0–1.0. Pydantic validation after the call is the only thing
  enforcing ranges, and `OUTPUT_RANGE_RULE` in `app/agents/base.py` states them
  in the prompt, which is what actually stopped it happening.
- **A retry at `temperature=0` with a fixed seed is a no-op.** It re-samples
  identically, so the mandated "one retry before marking an agent failed" would
  never change anything. `OllamaProvider.generate_json` offsets the seed by
  attempt number.
- **`num_ctx` must be pinned.** Ollama sizes the KV cache and compute buffers
  from the context window, and a model's default can be enormous (qwen2.5 ships
  32k). On an 8 GB host that allocation fails *before generation starts*, as an
  opaque HTTP 500. The counter-intuitive proof: `qwen2.5:1.5b` (~0.99 GB of
  weights) would not load while `llama3.2:1b` (~1.32 GB) ran fine. Model size on
  disk does not tell you whether it fits. `Settings.llm_num_ctx` = 8192.
- **The pytest suite does not exercise the Alembic migration.**
  `tests/conftest.py` builds the schema with `Base.metadata.create_all()`. A
  green run says nothing about migration correctness — that is precisely what
  let the Phase 1 migration bug survive undetected. Test migrations by booting
  `api` against a fresh volume.
- **Any new postgres enum in a migration needs `create_type=False`.** Otherwise
  `op.create_table` re-emits `CREATE TYPE` after the explicit `create()` and the
  migration dies with `DuplicateObject`. `0002` follows the pattern; copy it.

## Model selection (measured, not assumed)

One PRODUCT call on the seeded demo request, same prompt and evidence:

| Model | Latency | Findings | Grounded | Decision |
|---|---|---|---|---|
| `llama3.2:1b` | 295s | 9, all INFO | 0 | APPROVED |
| `qwen2.5:1.5b` | 244s | 5, all MEDIUM | 5 | REVISE |
| **`qwen2.5:3b`** (default) | **286s** | **3, all MEDIUM** | **3** | **REVISE** |
| `llama3` (8B) | — | will not load; ~5 GB of weights exceeds available RAM |

Latency barely separates the three that run, so this is a quality choice.
`llama3.2:1b` is unusable here — it echoed the taxonomy back as INFO
observations citing nothing, which the engine correctly but uselessly turned
into APPROVED. `qwen2.5:3b` is the committed default in `app/config.py`;
override with `LLM_MODEL` in `.env` on a host that can run something larger.

## Environment (Windows host, ~8 GB RAM)

- Project lives at `E:\MTG\buildgate\buildgate`. Notes referencing
  `C:\Users\<user>\Documents\MTG\buildgate`, `D:\Tai-Labs\buildgate`, or a
  `movin` user profile are stale.
- Docker CLI is on PATH. Ollama is at
  `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`. **`make` is not installed** — use
  the raw `docker compose` commands (README documents them).
- **Ollama must bind `0.0.0.0:11434`** to be reachable from the container; the
  default `127.0.0.1` bind is not. Models needed:
  `ollama pull nomic-embed-text` and `ollama pull qwen2.5:3b`.
- Host port 5432 is taken by an unrelated project, so `.env` sets
  `POSTGRES_HOST_PORT=5433`. Containers still reach the DB as `db:5432`.
- **Disk is a hazard.** C: has run out mid-build before, which also wedged the
  Docker engine until Docker Desktop was restarted. A cold `api` build needs
  >10 GB of scratch for torch wheels. `pip cache purge` and
  `npm cache clean --force` reclaimed ~13 GB last time.
- **RAM is the other hazard.** Free memory hovers around 1 GB with the stack up.
  See the `num_ctx` note above before blaming a model for being too large.

## Commands

```bash
docker compose up -d --build
docker compose exec api python -m app.scripts.seed_demo
docker compose exec -e DATABASE_URL=postgresql+psycopg://buildgate:buildgate@db:5432/buildgate_test api pytest -q
```

UI at http://localhost:3000, API at http://localhost:8000.

A full clean verification is `docker compose down -v && docker compose up -d
--build`, then seed, then tests, then a browser click-through. Budget ~5 minutes
for the review call itself.

## Other gotchas

- `db/init/01-create-test-db.sql` only runs on a *fresh* named volume. If
  `buildgate_test` is missing, `docker compose down -v` first.
- `NEXT_PUBLIC_API_BASE_URL` is baked in at Docker **build** time. Changing the
  API host or port needs a `web` image rebuild, not a restart.
- Nothing prevents a corpus from mixing embedding providers: if Ollama is down
  for one ingestion and up for another, chunks land in different vector spaces
  at the same 768 dimensions, and retrieval degrades silently rather than
  erroring. The provider used is recorded per document in the
  `DOCUMENT_INDEXED` audit payload — check there if retrieval looks wrong.
- A decision resolves once. A second accept or override returns 409. Re-running
  a review is the supported route to a different outcome: new `review_run_id`,
  new `decisions` row, previous rows untouched.

## Phase boundary rule

From `buildgate-phase-plan.md`, applies at the end of every phase. Do not begin
a phase while the previous one is broken:

1. Run the full test suite
2. Run the application from a clean `docker compose up`
3. Update `README.md`
4. Record architectural decisions and assumptions in `docs/DECISIONS.md`
5. Commit
