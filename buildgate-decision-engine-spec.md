# BuildGate — Decision Engine Specification

**Status: derived, reviewed once (2026-09-06), four questions still open for a
human — see "Unresolved" at the end.** This file was reconstructed from
`buildgate-core-requirements.md` (Feature 4) because the original spec was
referenced but absent from the repository. Every rule below traces to a stated
requirement; the *numeric thresholds* are the part that was never written down
and are proposed here. They live in configuration, so tuning them does not
touch engine code.

## Contract

```python
evaluate(inputs: DecisionInputs, thresholds: DecisionThresholds) -> DecisionResult
```

`evaluate()` is a **pure function**. No clock, no randomness, no database, no
network, no I/O. Identical inputs produce an identical result, byte for byte.
The LLM never selects the final status; it only supplies the structured agent
output that this function reads.

### Inputs

| Field | Type | Source |
|---|---|---|
| `reviews` | `list[AgentReviewInput]` | one per agent that returned |
| `expected_agents` | `frozenset[AgentType]` | agents the run was supposed to include |
| `deadline_is_fixed` | `bool` | the request field of the same name |

Each `AgentReviewInput` carries `agent`, `score` (0-100), `status`
(`PASS|WARNING|FAIL|BLOCK`), `confidence` (0.0-1.0),
`critical_information_missing`, `deadline_assessment`, and
`finding_severities` (the severity list drawn from `findings[]`).

`deadline_assessment` is meaningful only for `ENGINEERING`; the engine ignores
it on every other agent.

### Output

`DecisionResult` — `status` (`APPROVED|REVISE|BLOCKED`), `review_complete`,
`rule_ids` (every rule that fired, in evaluation order), and
`deciding_rule_id` (the one that set the status).

## Thresholds (proposed)

| Key | Default | Meaning |
|---|---|---|
| `confidence_floor` | `0.60` | a `BLOCK` at or above this is binding; below it downgrades |
| `warning_revise_threshold` | `3` | this many `WARNING` agents forces REVISE |
| `approve_min_average_score` | `75` | mean score required to approve |
| `approve_min_agent_score` | `60` | no single agent may score below this to approve |

## Evaluation order

Strict, **first match wins**: completeness -> BLOCK -> REVISE -> APPROVE ->
fallback. Every rule that matches is recorded in `rule_ids` even after the
status is decided, so a superseded blocker is never *discarded* — only
outranked. `deciding_rule_id` names the one that set the status.

### Stage 1 — Completeness

| Rule | Condition | Status |
|---|---|---|
| `C1_REVIEW_INCOMPLETE` | any expected agent did not return | REVISE |

This stage is what guarantees the requirement *"a review with any failed agent
can never produce APPROVE."*

Stage 1 is **structural completeness only** — did every expected reviewer come
back. `C2_CRITICAL_INFORMATION_MISSING` was originally here too and was moved to
stage 3 on 2026-09-06, because an agent reporting that *it* lacked information
is a judgement about the evidence, not about whether the review ran. Keeping it
in stage 1 let one reviewer's "I could not tell" outrank another reviewer's
confident CRITICAL block: on the seeded demo the board reported REVISE via `C2`
while `B2_CRITICAL_FINDING` sat unused behind it. It now reports BLOCKED via
`B2`, which is the path the phase plan names, and the evidence gap is still
recorded in `rule_ids`.

> **Open question, still unresolved.** An incomplete review (`C1`) that *also*
> contains a binding BLOCK still reports REVISE rather than BLOCKED. That is the
> literal reading of "completeness first" and is left as it is; the blocker
> remains in `rule_ids`. Unlike the `C2` case this has not yet bitten anything.

### Stage 2 — BLOCK

| Rule | Condition | Status |
|---|---|---|
| `B1_AGENT_BLOCK` | any agent `status == BLOCK` **and** `confidence >= confidence_floor` | BLOCKED |
| `B2_CRITICAL_FINDING` | any finding `severity == CRITICAL` on an agent with `confidence >= confidence_floor` | BLOCKED |
| `B3_INFEASIBLE_FIXED_DEADLINE` | `ENGINEERING.deadline_assessment == INFEASIBLE` **and** `deadline_is_fixed` | BLOCKED |

### Stage 3 — REVISE

| Rule | Condition | Status |
|---|---|---|
| `R1_LOW_CONFIDENCE_BLOCK` | any agent `status == BLOCK` with `confidence < confidence_floor` | REVISE |
| `R2_AGENT_FAIL` | any agent `status == FAIL` | REVISE |
| `C2_CRITICAL_INFORMATION_MISSING` | any agent set `critical_information_missing` | REVISE |
| `R3_MULTIPLE_WARNINGS` | count of `WARNING` agents `>= warning_revise_threshold` | REVISE |
| `R4_HIGH_SEVERITY_FINDING` | any finding `severity == HIGH` | REVISE |
| `R5_INFEASIBLE_FLEXIBLE_DEADLINE` | `ENGINEERING.deadline_assessment == INFEASIBLE` and **not** `deadline_is_fixed` | REVISE |
| `R6_DOUBTFUL_FIXED_DEADLINE` | `ENGINEERING.deadline_assessment == DOUBTFUL` **and** `deadline_is_fixed` | REVISE |
| `R7_LOW_CONFIDENCE_CRITICAL_FINDING` | any finding `severity == CRITICAL` on an agent with `confidence < confidence_floor` | REVISE |

`R1` implements *"a BLOCK below the confidence floor downgrades to a REVISE
trigger; it is never discarded"* — it downgrades the **status**, and the rule id
still appears in `rule_ids`.

`R7` is the same treatment for a CRITICAL *finding*, and exists because `B2` is
gated on the confidence floor. Gating `B2` that way is an extrapolation from the
BLOCK rule — the requirements do not mention confidence in connection with
finding severity — and without `R7` the extrapolation created a hole: a CRITICAL
finding from an unconfident agent matched no rule at all and could be APPROVED,
which discards it. `B1`/`R1` and `B2`/`R7` are now exact parallels.

There is deliberately **no** low-score REVISE rule. Score minimums are APPROVE
preconditions (stage 4), not REVISE triggers. This is what makes the fallback
reachable.

### Stage 4 — APPROVE

| Rule | Condition | Status |
|---|---|---|
| `A1_ALL_CLEAR` | review complete, no rule above fired, `mean(score) >= approve_min_average_score`, `min(score) >= approve_min_agent_score` | APPROVED |

### Stage 5 — Fallback

| Rule | Condition | Status |
|---|---|---|
| `F1_FALLBACK_REVISE` | nothing above matched | REVISE |

The fallback is **mandatory**. The requirements give the motivating case
directly: *no blocker, no fail, two warnings, average 65*. Two warnings is below
`warning_revise_threshold` (3) so no REVISE rule fires; average 65 is below
`approve_min_average_score` (75) so `A1` cannot fire. Without `F1` that input
matches nothing. This case is precisely why score minimums are APPROVE
preconditions rather than REVISE triggers.

## Truth table

All rows assume every expected agent returned unless stated otherwise. `conf` is
the confidence of the agent carrying the BLOCK.

| # | Input | Deciding rule | Status |
|---|---|---|---|
| 1 | one agent missing from the run | `C1_REVIEW_INCOMPLETE` | REVISE |
| 2 | all returned, one sets `critical_information_missing` | `C2_CRITICAL_INFORMATION_MISSING` | REVISE |
| 3 | agent BLOCK, `conf = 0.90` | `B1_AGENT_BLOCK` | BLOCKED |
| 4 | agent BLOCK, `conf = 0.60` (exactly the floor) | `B1_AGENT_BLOCK` | BLOCKED |
| 5 | CRITICAL finding, `conf = 0.80`, agent status WARNING | `B2_CRITICAL_FINDING` | BLOCKED |
| 6 | ENGINEERING INFEASIBLE, deadline fixed | `B3_INFEASIBLE_FIXED_DEADLINE` | BLOCKED |
| 7 | agent BLOCK, `conf = 0.59` (just under the floor) | `R1_LOW_CONFIDENCE_BLOCK` | REVISE |
| 8 | agent FAIL, all else PASS | `R2_AGENT_FAIL` | REVISE |
| 9 | three WARNING agents, avg 80 | `R3_MULTIPLE_WARNINGS` | REVISE |
| 10 | one HIGH finding, all agents PASS, avg 85 | `R4_HIGH_SEVERITY_FINDING` | REVISE |
| 11 | ENGINEERING INFEASIBLE, deadline not fixed | `R5_INFEASIBLE_FLEXIBLE_DEADLINE` | REVISE |
| 12 | ENGINEERING DOUBTFUL, deadline fixed | `R6_DOUBTFUL_FIXED_DEADLINE` | REVISE |
| 13 | ENGINEERING DOUBTFUL, deadline **not** fixed, else clean, avg 85 | `A1_ALL_CLEAR` | APPROVED |
| 14 | all PASS, avg 85, min 80 | `A1_ALL_CLEAR` | APPROVED |
| 15 | all PASS, avg 85, one agent scores 55 | `F1_FALLBACK_REVISE` | REVISE |
| 16 | **no blocker, no fail, two warnings, avg 65** | `F1_FALLBACK_REVISE` | REVISE |
| 17 | two warnings, avg 78, min 70 | `A1_ALL_CLEAR` | APPROVED |
| 18 | incomplete review **and** a binding BLOCK | `C1_REVIEW_INCOMPLETE` | REVISE (see open question) |
| 21 | one agent sets `critical_information_missing`, another raises a confident CRITICAL | `B2_CRITICAL_FINDING` | BLOCKED |
| 19 | CRITICAL finding, `conf = 0.50`, agent WARNING, avg 85 | `R7_LOW_CONFIDENCE_CRITICAL_FINDING` | REVISE |
| 20 | CRITICAL finding at any confidence, avg 100 | — | never APPROVED |

## Required tests

- Every truth-table row above, with mocked agent output and **no Ollama
  dependency**.
- Purity: 100 consecutive `evaluate()` calls on identical input return an
  identical result.
- A review with any failed agent never returns APPROVED.
- A low-confidence BLOCK appears in `rule_ids`, proving it was downgraded rather
  than discarded.
- A CRITICAL finding is never APPROVED at any confidence value.
- Thresholds are read from configuration, not hardcoded.

## Persistence

Each `evaluate()` result is written to `decisions` with `review_run_id`,
`policy_version`, `model_name`, `review_complete`, and `rule_ids`. Re-running a
review allocates a **new** `review_run_id` and inserts a new row; prior rows are
never updated or deleted.

`policy_version` changes whenever any rule or default threshold in this document
changes. Current value: **`2026.09.1`**.

## Unresolved — needs a human decision

The review on 2026-09-06 found and fixed one defect (`R7`, above). Three further
points are judgement calls that the requirements do not settle, and they are
left as they are rather than decided unilaterally.

1. **The four thresholds are invented.** `confidence_floor` 0.60,
   `warning_revise_threshold` 3, `approve_min_average_score` 75,
   `approve_min_agent_score` 60. Nothing in the requirements implies these
   numbers; they were chosen to be defensible and to make the stated fallback
   case reachable. They have never been validated against real review output.

2. **Stage ordering** (already noted above): completeness before BLOCK means an
   incomplete review containing a binding BLOCK reports REVISE.

3. **`deadline_assessment == UNKNOWN` fires no rule**, even against a
   contractually fixed deadline. So "engineering cannot tell whether this date
   is achievable" currently permits APPROVED. That may be right — UNKNOWN is not
   a negative finding — but on a *fixed* deadline it is arguably the same class
   of gap as `DOUBTFUL`, which does trigger `R6`. Deliberately left alone: the
   requirements list UNKNOWN as a valid value and never say what it should do.

4. **Confidence does not gate APPROVE.** An agent reporting PASS with score 90
   and `confidence 0.05` approves. Confidence is used only to weigh BLOCK and
   CRITICAL signals. Whether a uniformly unconfident board should be able to
   approve anything is a policy question, not a coding one.

Additionally, the requirements state that the decision screen shows
*"per-category scores, blockers, warnings, positive findings, required actions,
evidence references, and confidence"*. The UI shows all of these except
**positive findings**, which have no representation in the agent output schema
at all — every severity level (`INFO`…`CRITICAL`) describes a problem. Either
INFO is intended to carry that role, or the schema is missing a way for a
reviewer to record what is *good* about a request. Worth settling before the
other six agents are written against the same schema.
