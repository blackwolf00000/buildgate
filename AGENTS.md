# AGENTS.md — Resume Notes for BuildGate

This file exists so a future session (human or agent) can pick this work back up
without re-deriving context. Read this before touching the code.

## What this is

BuildGate, per `buildgate-core-requirements.md` (what to build) and
`buildgate-phase-plan.md` (the order to build it in). An AI governance layer
that challenges management requests before engineering capacity is committed,
running entirely on the customer's own machine.

**Phases 1 and 2 are complete and verified. Phase 3 is roughly half done.**
Working tree is clean at `8c24ca1`. **Backend suite: 108 passed.**

| Phase | State |
|---|---|
| 1 — Foundation and evidence pipeline | done, exit criteria ticked |
| 2 — Governance spine (one reviewer) | done, exit criteria ticked, boundary rule satisfied |
| 3 — Full review board | **in progress** — all seven agents built; demo determinism, privacy page and polish outstanding |

## How it fits together

Read `docs/DECISIONS.md` alongside this — it holds the *why* for everything
below, and there is a lot of it.

```
request + documents
  -> chunk -> embed (nomic-embed-text) -> pgvector
  -> ONE batched embedding pass for all agents' retrieval queries
  -> per-agent evidence                          (app/agents/base.py)
  -> schema-constrained call, temp 0, seed+attempt  (app/services/llm.py)
  -> evidence_id validation, fabricated ids stripped (app/services/evidence.py)
  -> agent_reviews rows                          (app/services/review.py)
  -> evaluate(), pure policy code                (app/services/decision_engine.py)
  -> decisions row + DECISION_CREATED
  -> a named human accepts / revises / overrides (app/services/decisions.py)
```

Load-bearing invariants, easy to break without noticing:

- **The model never picks the final status.** `evaluate()` does, and it is pure.
- **Evidence grounding is a code control.** Every `evidence_id` is checked
  against the chunks retrieved *for that specific agent call*.
- **The finding taxonomy is enforced by the JSON Schema**, not the prompt. Each
  agent's category codes become an `enum` on the finding's `category` field, so
  a reviewer is structurally unable to raise another reviewer's finding.
- **An adverse verdict needs a finding.** `AgentReviewOutput` rejects FAIL/BLOCK
  with an empty `findings` list, which makes `run_agent` retry.
- **A failed agent is recorded as failed**, and a review missing any expected
  agent can never APPROVE.
- **Review calls have no fallback.** (Embeddings do — a deliberate, visible
  exception reported via `GET /api/runtime`.)
- **The decision is a recommendation** until a named human acts.

## Phase 3 — where it stands

### Done

All seven reviewers exist and are registered in `app/agents/__init__.py`:
`PRODUCT`, `SECURITY`, `ENGINEERING`, `ARCHITECTURE`, `QA`, `BA`,
`USER_EVIDENCE`. Each has its own retrieval query, role framing (stated
negatively as well as positively), and finding taxonomy. `docs/DECISIONS.md`
records where the boundaries between them are drawn.

Differentiation holds. Measured pairwise title overlap across the full board is
**max 0.12 Jaccard**; ARCHITECTURE vs ENGINEERING, the pair the plan warns about
most, is 0.00–0.11. A test asserts no two agents share a category beyond
`INJECTION_ATTEMPT`, which is deliberately universal.

Two engine changes came out of running the real board:

- `C2_CRITICAL_INFORMATION_MISSING` moved from stage 1 to stage 3, because one
  reviewer's "I could not tell" was outranking another's confident CRITICAL and
  the demo reported REVISE instead of BLOCKED.
- `R7_LOW_CONFIDENCE_CRITICAL_FINDING` added, because a CRITICAL finding from an
  agent below the confidence floor previously matched no rule at all.

### The open problem — read this before running anything

**The demo does not currently produce BLOCK, and the last fix for it is
unverified.**

Sequence of what happened, because the two effects are easy to confuse:

1. First full board run: every agent returned FAIL, six at confidence 1.0, two
   with empty findings. SECURITY *did* return CRITICAL, so the board BLOCKed via
   `B2_CRITICAL_FINDING` — the path `buildgate-phase-plan.md` names.
2. Quality fixes went in (verdict/severity mapping, confidence calibration,
   evidence required at MEDIUM+). These worked: verdicts spread to WARNING,
   confidence fell to 0.9–0.95, empty adverse verdicts stopped,
   ENGINEERING/QA/SECURITY grounded every finding, overlap fell to 0.12.
3. **But the same change biased severity downward.** The rule said "most reviews
   end here" at WARNING and "reserve FAIL and BLOCK". SECURITY duly downgraded
   the mandatory Data Governance sign-off from CRITICAL to MEDIUM, `B2` stopped
   firing, and the board settled on REVISE via `R3_MULTIPLE_WARNINGS`.
4. `VERDICT_COHERENCE_RULE` in `app/agents/base.py` was then reworded to say it
   governs *which status follows from a severity* and is explicitly not an
   instruction to prefer low severities, plus "a control the evidence states as
   mandatory ... is CRITICAL — do not soften it".

**Step 4 has never been run against the model.** The confirming run died on an
unrelated Ollama out-of-memory error (`/api/embeddings` 500). First job on
resume: re-run the board and check whether SECURITY returns CRITICAL again.
`scratchpad/differentiation.py` was the harness for this (it is a scratch file,
not in the repo — rewrite or recreate it; it just loops `AGENT_REGISTRY`,
prints each agent's findings, and computes pairwise title overlap).

Watch for the underlying tension: the same prompt has to spread verdicts *and*
let a genuine policy violation reach CRITICAL. If rewording cannot hold both,
the honest options are to move the severity judgement into each agent's own
`scoring_guidance` rather than the shared rule, or accept a demo that REVISEs
and say so.

### Not built

- **Demo determinism.** No `tests/fixtures/demo_run.json`, no snapshot test
  locking the BLOCK outcome. The plan wants both, and "produces BLOCK across
  repeated runs" is unproven — the outcome has changed twice already.
- **Privacy page.** Deployment mode, AI runtime, endpoint, database, upload
  location, and a *measured* external-call count from the outbound wrapper
  (`app/services/http_client.py` already counts allowed/rejected; the number
  must not be hardcoded).
- **Polish.** Loading and error states throughout, consistent badge styling,
  README demo walkthrough, limitations section stating plainly that there is no
  authentication and `approved_by` is free text.
- **The five-minute demo target.** Seven sequential agents take **~17–25
  minutes** on this host. The exit criterion says under five. Options: run
  agents concurrently (they are independent, but contend for one Ollama process
  — measure before assuming a speedup), cut the board, shrink prompts, or revise
  the target. The plan's own "if behind" clause permits shipping five agents
  rather than seven poorly differentiated ones; differentiation is currently
  fine, so that clause does not apply as written.

### Phase 3 exit criteria

| Criterion | State |
|---|---|
| All seven agents return schema-valid output | ✅ |
| A reader can identify which agent wrote a finding without the label | ✅ max overlap 0.12 |
| Seeded scenario produces BLOCK across repeated runs | ❌ see open problem |
| Snapshot test locks the demo outcome | ❌ not built |
| Privacy page shows a measured external-call count | ❌ not built |
| Full demo runs end to end in under five minutes | ❌ ~17–25 min |
| All Definition of Done items checked | ❌ |

## Open questions needing a human answer

`buildgate-decision-engine-spec.md` was referenced by the requirements but
absent, so it was derived and is marked "reviewed once, four questions open".
Two were settled in this session (`R7`; `C2` moved to stage 3). Still open:

1. **The four thresholds are invented** — `confidence_floor` 0.60,
   `warning_revise_threshold` 3, `approve_min_average_score` 75,
   `approve_min_agent_score` 60. They live in `app/config.py`.
2. **`C1` still sits in stage 1**, so an *incomplete* review containing a
   binding BLOCK reports REVISE. Unlike the `C2` case this has not bitten
   anything yet.
3. **`deadline_assessment == UNKNOWN` fires no rule**, even against a fixed
   deadline.
4. **Confidence does not gate APPROVE.**

Separately: the requirements say the decision screen shows *"positive
findings"*, which have **no representation in the agent output schema** — every
severity from INFO to CRITICAL describes a problem. Worth settling before more
is built on the schema.

## Findings worth not rediscovering

- **Ollama's `format` does not enforce numeric ranges**, only structure and
  types. `llama3.2:1b` returned `"confidence": 100` for a 0.0–1.0 field.
  Pydantic is the only thing enforcing ranges; `OUTPUT_RANGE_RULE` states them
  in the prompt, which is what stops it happening.
- **A retry at `temperature=0` with a fixed seed is a no-op.**
  `OllamaProvider.generate_json` offsets the seed by attempt number.
- **`num_ctx` must be pinned.** Ollama sizes the KV cache from the context
  window and a model's default can be enormous (qwen2.5 ships 32k). On this host
  that fails *before generation starts*, as an opaque HTTP 500. The
  counter-intuitive proof: `qwen2.5:1.5b` (~0.99 GB) would not load while
  `llama3.2:1b` (~1.32 GB) ran fine. `Settings.llm_num_ctx` = 8192.
- **Never interleave embedding and generation per agent.** They are different
  Ollama models; alternating makes Ollama evict and reload one at every step,
  which on this host timed the embedding call out mid-run.
  `collect_evidence_for_all` batches all retrieval first. This also cut
  per-agent latency from ~286s to ~140–160s, because the review model stays
  resident.
- **The pytest suite does not exercise the Alembic migration.**
  `tests/conftest.py` uses `Base.metadata.create_all()`. A green run says
  nothing about migration correctness — that is what let the Phase 1 migration
  bug survive. Test migrations by booting `api` against a fresh volume.
- **Any new postgres enum in a migration needs `create_type=False`**, or
  `op.create_table` re-emits `CREATE TYPE` and the migration dies. `0002`
  follows the pattern.
- **`docker compose exec api pytest` runs the image's copy of the tests.**
  Rebuild (`docker compose up -d --build api`) after editing test files, or you
  will debug stale failures.

## Environment (Windows host, ~8 GB RAM)

- Project lives at `E:\MTG\buildgate\buildgate`. Notes referencing
  `C:\Users\<user>\Documents\MTG\buildgate`, `D:\Tai-Labs\buildgate`, or a
  `movin` user profile are stale.
- Docker CLI is on PATH. Ollama is at
  `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`. **`make` is not installed** — use
  the raw `docker compose` commands (README documents them).
- **Ollama must bind `0.0.0.0:11434`** to be reachable from the container.
  Models: `ollama pull nomic-embed-text` and `ollama pull qwen2.5:3b`.
- **RAM is the binding constraint.** Free memory sits near 0.5–1.5 GB with the
  stack up. Ollama OOM appears as an opaque HTTP 500 on `/api/generate` *or*
  `/api/embeddings` — if a call fails in seconds rather than minutes, suspect
  memory before suspecting the code. `docker compose stop web` frees ~1 GB when
  running the board manually.
- Host port 5432 is taken by an unrelated project, so `.env` sets
  `POSTGRES_HOST_PORT=5433`.
- **Disk is a hazard.** C: has run out mid-build before, wedging the Docker
  engine until Docker Desktop was restarted. A cold `api` build needs >10 GB of
  scratch for torch wheels.

## Model selection (measured)

One PRODUCT call on the demo request, same prompt and evidence:

| Model | Latency | Findings | Grounded | Decision |
|---|---|---|---|---|
| `llama3.2:1b` | 295s | 9, all INFO | 0 | APPROVED |
| `qwen2.5:1.5b` | 244s | 5, all MEDIUM | 5 | REVISE |
| **`qwen2.5:3b`** (default) | **286s**¹ | **3, all MEDIUM** | **3** | **REVISE** |
| `llama3` (8B) | — | will not load; ~5 GB of weights exceeds available RAM |

¹ measured before retrieval batching; now ~140–160s per agent.

`qwen2.5:3b` is the committed default in `app/config.py`; override with
`LLM_MODEL` in `.env`.

## Commands

```bash
docker compose up -d --build
docker compose exec api python -m app.scripts.seed_demo
docker compose exec -e DATABASE_URL=postgresql+psycopg://buildgate:buildgate@db:5432/buildgate_test api pytest -q
```

UI at http://localhost:3000, API at http://localhost:8000. A full clean
verification is `docker compose down -v && docker compose up -d --build`, then
seed, tests, browser click-through. Budget ~20 minutes if a full board review is
part of it.

## Other gotchas

- `db/init/01-create-test-db.sql` only runs on a *fresh* named volume. If
  `buildgate_test` is missing, `docker compose down -v` first.
- `NEXT_PUBLIC_API_BASE_URL` is baked in at Docker **build** time.
- Nothing prevents a corpus from mixing embedding providers: chunks would land
  in different vector spaces at the same 768 dimensions and retrieval would
  degrade silently. The provider used is recorded per document in the
  `DOCUMENT_INDEXED` audit payload.
- A decision resolves once; a second accept or override returns 409. Re-running
  a review is the supported route to a different outcome.

## Phase boundary rule

From `buildgate-phase-plan.md`. Do not begin a phase while the previous one is
broken:

1. Run the full test suite
2. Run the application from a clean `docker compose up`
3. Update `README.md`
4. Record architectural decisions and assumptions in `docs/DECISIONS.md`
5. Commit
