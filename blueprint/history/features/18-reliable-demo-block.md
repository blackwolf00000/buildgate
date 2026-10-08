# Feature: Reliable demo BLOCK

**From build-plan:** feature 18
**Build attempt:** 1
**Branch:** feature/reliable-demo-block
**Status:** verified

## Goal

The seeded demo request ("Self-service customer data export button") produces a
**BLOCKED** decision via `B2_CRITICAL_FINDING` on repeated full-board runs:
SECURITY raises a CRITICAL finding, at or above the confidence floor, grounded in
an evidence id from `security-policy.md` (the Data Governance sign-off). If that
cannot be achieved honestly, the outcome is measured, recorded, and the demo
narrative is changed to match, rather than forced.

## In scope

- A repeatable board harness that runs the full seven-agent review on the seeded
  request and prints, per run: each agent's status, score, confidence, finding
  severities and categories with evidence ids, the fired rule ids, and the final
  decision status. Also prints pairwise finding-title overlap (Jaccard), so
  differentiation does not regress silently.
- A first measured run of the board with the current, unconfirmed
  `VERDICT_COHERENCE_RULE` reword.
- If SECURITY does not return a grounded CRITICAL: prompt changes, tried in this
  order and measured after each:
  1. tighten SECURITY's own `scoring_guidance` (`app/agents/security.py`);
  2. move severity judgement out of the shared `VERDICT_COHERENCE_RULE` into the
     per-agent `scoring_guidance` where needed.
- Confirmation across **3 consecutive full-board runs** on a freshly seeded
  request (see Open questions).
- Recording the result and any prompt changes in `docs/DECISIONS.md`, and
  updating `AGENTS.md` "Known open problems" to the measured state.

## Out of scope

- The demo fixture `tests/fixtures/demo_run.json` and snapshot test (feature 19).
- Latency work or model changes (feature 22). `qwen2.5:3b` stays the model.
- README walkthrough and UI polish (feature 20).
- Any change to `decision_engine.py` rules, ordering, or thresholds to make the
  demo BLOCK. The engine is policy; the demo must earn its outcome. The open
  engine questions (`C1` stage, `UNKNOWN` deadline, etc.) stay open.
- Editing `data/demo/*.md` to make the policy louder. The seeded evidence is the
  test input; changing it to pass is gaming the result. (If you believe a demo
  document is genuinely wrong, stop and ask.)

## Build loop

Config: `workflow.stepReview: "feature"`, `checkpointCommits: "disabled"`. Build
all steps, then one review packet for the whole feature. No checkpoint commits;
`/complete` creates the feature commit. Each board run takes ~12-17 minutes on
this host, so steps 2-4 are long-running; run them in the background and report
measured numbers only.

## Build steps

- [x] **1. Board harness.** Add `backend/app/scripts/board_run.py`, invoked as
  `docker compose exec api python -m app.scripts.board_run [--runs N]`. It finds
  the seeded demo request by title (exits non-zero with a clear message if it is
  not seeded), calls the existing `start_review` / `execute_review` path in
  `app/services/review.py` synchronously, then reads back `agent_reviews` and the
  `decisions` row for that `review_run_id` and prints the summary above. It
  creates normal review runs and decisions (no shortcuts around the service), so
  audit events are written exactly as from the UI. Pure helpers (overlap
  computation, summary formatting from review rows) live in the script and are
  unit-tested.
  - Done when: `pytest -q` passes with new tests for the overlap and summary
    helpers (fake rows, no Ollama), and the script exits non-zero with its
    message against an unseeded database.

- [x] **2. Baseline measurement.** Rebuild `api`, seed, run the harness once
  against Ollama with the current prompts.
  - Done when: the full printed output of one run is captured in the review
    packet, stating whether SECURITY returned a grounded CRITICAL and which rules
    fired. If it already BLOCKs via `B2`, skip step 3.

- [x] **3. Prompt adjustment (only if step 2 did not BLOCK via B2).** _Skipped: step 2 BLOCKed via B2._ Apply the
  smallest change from the ordered list in scope, re-run, repeat. Stop after
  three attempts without success and take the fallback in step 4.
  - Done when: one run BLOCKs via `B2` with the SECURITY CRITICAL citing a
    `security-policy.md` evidence id, the backend suite is green, and max
    pairwise title overlap is still at or below ~0.12 (report the number).

- [x] **4. Repeat-run confirmation and record.** Run the harness with `--runs 3`.
  Record results in `docs/DECISIONS.md` (prompt changes, measured per-run outcome,
  overlap, and timing) and update `AGENTS.md` "Known open problems".
  - Done when: 3/3 runs BLOCK via `B2`, **or** the fallback is recorded: the
    measured outcomes, why BLOCK was not reliably reached, and an explicit note
    that the demo narrative must be revised (left to the user to decide before
    feature 19).

## Files / areas

- `backend/app/scripts/board_run.py` (new), `backend/tests/test_board_run.py` (new)
- `backend/app/agents/security.py`, `backend/app/agents/base.py`; other
  `backend/app/agents/*.py` only if step 3 moves severity guidance into them
- Read-only: `backend/app/services/review.py`, `decision_engine.py`,
  `app/scripts/seed_demo.py`, `data/demo/security-policy.md`
- `docs/DECISIONS.md`, `AGENTS.md`

## Data / contracts

- No schema, API, or migration changes. Harness runs persist ordinary
  `review_runs`, `agent_runs`, `agent_reviews`, `decisions`, and audit rows.
- Agent output schema, finding taxonomies, and the "adverse verdict needs a
  finding" validation must stay unchanged.
- Harness output is stdout text for humans; not a stable contract (feature 19
  defines the fixture format).

## Testing

- Test command (AGENTS.md): rebuild `api`, then
  `docker compose exec -e DATABASE_URL=postgresql+psycopg://buildgate:buildgate@db:5432/buildgate_test api pytest -q`.
- New unit tests for harness helpers only. Model behaviour is evidenced by
  captured harness output, not tests.
- Existing `test_decision_engine.py` and the taxonomy-overlap test must stay
  green; any prompt change must not break them.
- No browser evidence required; optionally confirm the BLOCKED badge on
  `/requests/[id]` after a successful run.

## Notes for the AI

- Ollama must be up on `0.0.0.0:11434` with `qwen2.5:3b` and `nomic-embed-text`.
  Free RAM first (`docker compose stop web`). An HTTP 500 that fails in seconds
  is memory, not code.
- Do not interleave embeddings and generation; use the existing service path,
  which already batches retrieval and releases the model.
- Temperature 0 with fixed seed makes repeated runs near-identical; "3/3" mostly
  proves stability, not robustness. Say so in the record.
- The tension to respect: the shared rule must still spread verdicts (not every
  agent FAIL at 1.0 confidence). Report each agent's status/confidence spread
  alongside the SECURITY result.
- Report only numbers you measured. Never claim a BLOCK from one run as reliable.

## Open questions

- **How many runs is "reliable"?** Spec assumes 3 consecutive runs. Change it
  before implementation if you want more (each run costs ~15 minutes).
- **If BLOCK cannot be reached honestly**, the fallback records it and stops.
  Choosing the revised demo narrative (accept REVISE, cut the board, or change
  the model) is your decision afterwards, not this feature's.


<!-- blueprint:completion {"schemaVersion":2,"specBytes":7391,"specSha256":"e9def327e343fc5d8a729e49c9aef8016c5a20a33dab2b656c3a33d9d308833c","branch":"refs/heads/feature/reliable-demo-block","head":"cdb17d50f9632d15b3caa682a1939ad9fb041a8f","baseRef":"refs/heads/main","baseCommit":"cdb17d50f9632d15b3caa682a1939ad9fb041a8f","sourceTree":"fb2e0c24eb5db90374e17be02436d6c9431b890e","landing":"local-merge","absentOptional":[]} -->
