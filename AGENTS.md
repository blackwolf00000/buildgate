# AGENTS.md

Instructions for AI coding agents working in this project. This is the cross-tool
entry point. Codex, Google Antigravity, and OpenCode read `AGENTS.md`. Other
compatible tools do too. Claude Code reads `CLAUDE.md`, which imports this file,
so there is a single source of truth.

Claude Code, Codex, and every other AI tool must not add AI attribution to
commits or pull requests, including AI `Co-Authored-By` trailers or generated-by
signatures. Preserve genuine human attribution. See
[Commit and PR attribution](blueprint/context/ai-interaction.md#commit-and-pr-attribution)
for optional tool settings.

## What this is

**BuildGate** is an AI governance layer that challenges management requests
before engineering capacity is committed, running entirely on the customer's own
machine. A manager submits a request with supporting documents; seven local AI
reviewers assess it against that evidence; deterministic policy code computes
APPROVE / REVISE / BLOCK; a named human accepts, sends for revision, or
overrides, and every step lands in an append-only audit trail.

The product source documents are `buildgate-core-requirements.md` (what to
build), `buildgate-phase-plan.md` (the order), `buildgate-decision-engine-spec.md`
(rules, thresholds, truth table) and `docs/DECISIONS.md` (the *why* behind
nearly every choice below; read it alongside this file). The Blueprint plans in
`blueprint/` were adopted from these, not the other way round.

This project uses the **AI Blueprint**, a workflow layer, not an app skeleton.
It was overlaid on an existing app. Never run a framework scaffolder here. The
workflow is defined by the local skills and context files below.

## How BuildGate fits together

```
request + documents
  -> chunk -> embed (nomic-embed-text) -> pgvector
  -> ONE batched embedding pass for all agents' retrieval queries
  -> per-agent evidence                              (app/agents/base.py)
  -> schema-constrained call, temp 0, seed+attempt   (app/services/llm.py)
  -> evidence_id validation, fabricated ids stripped (app/services/evidence.py)
  -> agent_reviews rows, persisted as each arrives   (app/services/review.py)
  -> evaluate(), pure policy code                    (app/services/decision_engine.py)
  -> decisions row + DECISION_CREATED
  -> a named human accepts / revises / overrides     (app/services/decisions.py)
```

Paths are relative to `backend/`. The seven reviewers (`PRODUCT`, `SECURITY`,
`ENGINEERING`, `ARCHITECTURE`, `QA`, `BA`, `USER_EVIDENCE`) are registered in
`app/agents/__init__.py`.

### Load-bearing invariants

Easy to break without noticing:

- **The model never picks the final status.** `evaluate()` does, and it is pure:
  no clock, randomness, or database.
- **Evidence grounding is a code control.** Every `evidence_id` is checked
  against the chunks retrieved *for that specific agent call*.
- **The finding taxonomy is enforced by the JSON Schema**, not the prompt. Each
  agent's category codes become an `enum` on the finding's `category` field, so
  a reviewer is structurally unable to raise another reviewer's finding. A test
  asserts no two agents share a category except `INJECTION_ATTEMPT`, which is
  deliberately universal.
- **An adverse verdict needs a finding.** `AgentReviewOutput` rejects FAIL/BLOCK
  with an empty `findings` list, which makes `run_agent` retry.
- **A failed agent is recorded as failed**, and a review missing any expected
  agent can never APPROVE.
- **Review calls have no fallback.** No cloud model, ever. Embeddings do have a
  local sentence-transformers fallback, a deliberate, visible exception reported
  via `GET /api/runtime`.
- **All outbound HTTP goes through one wrapper** (`app/services/http_client.py`)
  with a host allowlist and allowed/rejected counters.
- **The decision is a recommendation** until a named human acts. A decision
  resolves once; a second accept or override returns 409. Re-running a review
  creates a new `review_run_id` and never overwrites prior rows.

### Known open problems

- **The demo does not reliably BLOCK.** The phase plan wants the seeded scenario
  to BLOCK via `B2_CRITICAL_FINDING` (SECURITY CRITICAL citing
  `security-policy.md`). A verdict-quality fix biased severity downward,
  SECURITY softened the mandatory Data Governance sign-off to MEDIUM, and the
  board settled on REVISE via `R3_MULTIPLE_WARNINGS`. `VERDICT_COHERENCE_RULE`
  in `app/agents/base.py` was reworded to stop that, but **the reword has never
  been confirmed against the model**. The tension: one shared prompt has to
  spread verdicts *and* let a genuine policy violation reach CRITICAL. If
  rewording cannot hold both, move the severity judgement into each agent's own
  `scoring_guidance`, or accept a demo that REVISEs and say so.
- **No demo fixture or snapshot test** (`tests/fixtures/demo_run.json`).
- **Board latency.** Sequential agents now take ~100-145s each, so a full board
  is still well over the five-minute demo target. Concurrency exists
  (`review_concurrency`) but defaults to 1: at 3 it was markedly worse on this
  host, because CPU inference here is memory-bandwidth bound. Faster models
  (`qwen2.5:0.5b`) stop actually reviewing.
- **The single-container Hugging Face image is unbuilt.** The root `Dockerfile`
  and `start.sh` (see `HUGGINGFACE-DEPLOY.md`) have only been read, never built
  or run.
- **Engine questions still open** (see `buildgate-decision-engine-spec.md`): the
  four thresholds in `app/config.py` are invented; `C1` still sits in stage 1, so
  an incomplete review with a binding BLOCK reports REVISE;
  `deadline_assessment == UNKNOWN` fires no rule; confidence does not gate
  APPROVE. The requirements' "positive findings" have no representation in the
  agent output schema.

### Findings worth not rediscovering

- **Ollama's `format` does not enforce numeric ranges**, only structure and
  types. `llama3.2:1b` returned `"confidence": 100` for a 0.0-1.0 field.
  Pydantic enforces ranges; `OUTPUT_RANGE_RULE` states them in the prompt.
- **A retry at `temperature=0` with a fixed seed is a no-op.**
  `OllamaProvider.generate_json` offsets the seed by attempt number.
- **`num_ctx` must be pinned** (`llm_num_ctx`, currently 3072). Ollama sizes the
  KV cache from it and a model's default can be enormous (qwen2.5 ships 32k),
  which fails *before generation starts* as an opaque HTTP 500.
- **Unload with the options you loaded with.** `release()` must pass the same
  `num_ctx`, or Ollama starts a second runner at the default window just to
  unload, and later calls fail with "failed to allocate compute pp buffers".
- **Never interleave embedding and generation per agent.** They are different
  Ollama models; alternating makes Ollama evict and reload one at every step.
  `collect_evidence_for_all` batches all retrieval first, and `keep_alive` keeps
  the review model resident between agents.
- **Review runs are in-process background tasks.** An API restart orphans them;
  `recover_orphaned_runs()` fails them with `RunInterrupted` on startup.
- **The pytest suite does not exercise the Alembic migration.**
  `tests/conftest.py` uses `Base.metadata.create_all()`. Test migrations by
  booting `api` against a fresh volume.
- **Any new postgres enum in a migration needs `create_type=False`**, or
  `op.create_table` re-emits `CREATE TYPE` and the migration dies.
- **`docker compose exec api pytest` runs the image's copy of the tests.**
  Rebuild (`docker compose up -d --build api`) after editing tests or app code.

### Model selection (measured)

`qwen2.5:3b` is the default reviewer (`app/config.py`, override with
`LLM_MODEL`). On one PRODUCT call: `llama3.2:1b` returned 9 INFO findings, none
grounded, and APPROVED; `qwen2.5:1.5b` and `qwen2.5:3b` both grounded every
finding and returned REVISE; `llama3` (8B) will not load on an ~8 GB host.

### Environment (Windows host, ~8 GB RAM)

- Project lives at `E:\MTG\buildgate`. Notes referencing other paths are stale.
- Docker CLI is on PATH. Ollama is at `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`
  and **must bind `0.0.0.0:11434`** to be reachable from the containers.
  Models: `ollama pull nomic-embed-text` and `ollama pull qwen2.5:3b`.
- **`make` is not installed.** Use the raw `docker compose` commands below.
- **RAM is the binding constraint.** Ollama OOM appears as an opaque HTTP 500 on
  `/api/generate` *or* `/api/embeddings`. If a call fails in seconds rather than
  minutes, suspect memory before code. `docker compose stop web` frees ~1 GB.
- Host port 5432 is taken by an unrelated project, so `.env` sets
  `POSTGRES_HOST_PORT=5433`.
- **Disk is a hazard.** C: has run out mid-build, wedging Docker until Docker
  Desktop restarted. A cold `api` build needs >10 GB of scratch for torch
  wheels; the HF image build exhausted the disk twice.

### Other gotchas

- `db/init/01-create-test-db.sql` only runs on a *fresh* named volume. If
  `buildgate_test` is missing, `docker compose down -v` first.
- `NEXT_PUBLIC_API_BASE_URL` is baked in at Docker **build** time.
- Nothing prevents a corpus from mixing embedding providers; chunks would land
  in different vector spaces at the same 768 dimensions and retrieval would
  degrade silently. The provider is recorded per document in the
  `DOCUMENT_INDEXED` audit payload.

### Phase boundary rule

From `buildgate-phase-plan.md`. Do not begin new work while the previous slice
is broken. At each boundary: run the full test suite, run the app from a clean
`docker compose up`, update `README.md`, record decisions and assumptions in
`docs/DECISIONS.md`, then commit.

## Proportional engineering

Build for established requirements, not hypothetical scale, threats, or future
flexibility. Reuse existing code, the standard library, native platform features,
and installed dependencies before adding machinery.

- Unknown scale or extensibility defaults to the smaller reversible design. Do
  not infer enterprise, multi-tenant, hostile-user, or compliance requirements.
- Derive trust and data-integrity boundaries from actual reachability: untrusted
  input, auth/session/ownership, shared persisted data, destructive operations,
  payments, secrets, and sensitive data.
- Ask only when an unknown materially changes behavior, architecture, persisted
  data, interoperability, a real security boundary, or cost. Otherwise choose the
  simplest repository-native implementation.
- Add an abstraction, dependency, service, configuration surface, compatibility
  layer, or security mechanism only for a current requirement.
- Simplicity never removes real trust-boundary validation, data-loss prevention,
  accessibility, explicit security requirements, configured tests, or project rules.
- Stack-specific template standards apply only when the project uses that stack.

## Read these when relevant

- `blueprint/config.json` - deterministic project workflow settings
- `blueprint/context/project-overview.md` - the project's source of truth
- `blueprint/context/coding-standards.md` - read before changing code
- `blueprint/context/ai-interaction.md` - read when running the Blueprint workflow
- `blueprint/context/current-feature.md` - the one feature, fix, or rollback being built in this checkout

Reuse relevant context already loaded in the session. Claude Code imports only
this file; its Blueprint skills load the other files on demand.

## Project configuration

`blueprint/config.json` is the user-owned, machine-readable workflow policy for
this project. Workflow skills read the relevant settings before acting. A
missing file means built-in defaults. An invalid file falls back to defaults for
read-only status reporting, but mutating workflow commands stop and point to
`/doctor` instead of guessing.

Configuration can make review or verification stricter and can tune local
branch names and automated-mode limits. It never grants permission to commit,
merge, push, deploy, publish, send, delete data, waive a failing check, or accept
a finding. Those approval and safety boundaries are not configurable.

`qualityGates.regular` controls automatic audit, independent-review, check, and
try-guide behavior for the normal workflow and Autopilot.
`qualityGates.continuous` controls the same per-feature gates for Continuous
Mode. The existing `tryGuide` keys select `/check guide`, which generates
instructions without performing verification or recording acceptance.
Independent review defaults to `when-sensitive` in both workflows, while
audit, check, and try guide default to `manual`. Sensitive or unusually broad
work therefore selects independent review automatically; ordinary small work
does not. Setting a workflow's independent review to `manual` disables that
automatic selection, while an explicit `/audit independent current` remains
available. The other conditional modes are `when-sensitive` for audit,
`when-behavioral` for check, and `when-user-facing` for try guides. `always`
runs the gate for every work item in that workflow.

`review.independentExecution` controls how a selected independent-review gate
runs. Its default, `automatic`, uses a fresh isolated reviewer child when the
active adapter can prove isolation, exact reviewer identity and model, and
completion. Otherwise it preserves the request and falls back to the manual
handoff. This setting changes execution only; the quality-gate policy still
decides whether review is selected.
The automatic path spawns a generic child through the current runtime and gives
it the installed project-local Audit skill and review contract. It never requires
or discovers global agent roles, skills, prompts, or TraversyFlow components.
New review requests record requested execution and completed receipts record
actual execution. Manual uses `fresh session`; automatic uses `fresh subagent`;
an explicit automatic fallback records actual manual with `fresh session`.

`git.landing` controls only how `/complete` offers to land finished regular
work. Its default, `local-merge`, keeps the local squash-merge flow. Set it to
`pull-request` when completed branches should be pushed and opened as pull
requests for provider review and squash merge. Configuration never supplies the
required push, pull-request, or merge approvals. Continuous Mode remains
local-only and ignores this setting.

New projects default to one review packet after all small implementation steps
(`workflow.stepReview: "feature"`) with step checkpoint commits disabled. This
keeps the normal loop reviewable without repeating the full session context after
every step. Set `stepReview` to `every` when teaching, pairing closely, or working
on a high-risk change. That restores the per-step approval pauses. To fully
restore the previous workflow, including optional checkpoint prompts after an
approved step, also set `checkpointCommits` to `enabled`. Onboarding presents
these pairs as Efficient and Guided choices, but stores only the two low-level
settings. They can be changed at any time. Both styles end with an optional
read-only code walkthrough. Review cadence controls approval pauses, not whether
the user can ask for an explanation of the finished implementation.

## Workflow

Build one feature, fix, or rollback at a time, behind review gates. Each step's instructions
are plain markdown skills any capable agent can read and follow. The workflow is
exposed through tool-specific adapters:

- Codex: `.agents/skills/<skill>/SKILL.md`
- Claude Code: `.claude/skills/<skill>/SKILL.md`
- GitHub Copilot: `AGENTS.md` plus `.agents/skills/<skill>/SKILL.md`
- Google Antigravity: `AGENTS.md` plus `.agents/skills/<skill>/SKILL.md`
- OpenCode: `AGENTS.md` plus the compatible `.agents/skills/` or
  `.claude/skills/` tree already installed for the selected tools

Unused adapters can be removed. Codex and GitHub Copilot share `.agents/`, and
Google Antigravity uses that tree too. OpenCode can reuse `.agents/` or
`.claude/`. Projects without Claude Code can delete `CLAUDE.md` and `.claude/`.
Claude Code-only projects can delete `.agents/`, but should keep `AGENTS.md`
because `CLAUDE.md` imports it. Do not create `.opencode/skills/` or an
Antigravity-specific skill tree. Both tools use the supported shared trees.

When changing shared workflow behavior, update the matching skill in both
adapter folders so every supported tool stays aligned.

### Parallel work

Blueprint supports parallel work through isolated Git checkouts, without a
separate team mode. Give each developer or agent its own clone or Git worktree
and one dedicated branch before starting `/feature` or `/fix`. The branch must
use the configured prefix and the work item's lowercase kebab-case title. Each
checkout keeps its own
`blueprint/context/current-feature.md`, findings, and review state. Never run two
active work items in the same working directory or replace another worker's
active spec.

Parallel branches may both update `blueprint/build-plan.md`; resolve any normal
Git conflict when the later branch lands. Use `git.landing: "pull-request"` when
the default branch is protected or several isolated checkouts are active. This
model intentionally does not add per-item state folders or automatic agent
coordination.

Learn the feature loop: `/feature` -> `/implement` -> `/check` -> `/audit current` ->
`/complete`. Approve the Feature spec before Implement. Check proves behavior;
Audit reviews code and records findings. Showing both in this path does not
change configured gates or make Audit mandatory. `/check guide` only generates
manual instructions and never performs verification or records acceptance.

Core skills:

### Build

- `feature` - turn a build-plan item into a spec, or propose a reviewed plan addition for a genuinely new feature
- `implement` - build the current spec one small, reviewed step at a time
- `check` - prove the current spec against the running app, or use `check guide`
  for a read-only manual review guide: where to go, what to click, what to expect
- `complete` - run the final safety pass, log features, fixes, or rollbacks under `blueprint/history/`, then request approval for the configured local merge or pull-request landing

### Understand and review

- `explore` - investigate an idea against the actual code without writing files or requiring plans
- `brief` - read-only briefing on an upcoming build-plan feature (scope, dependencies, size) before you spec it
- `status` - read-only progress summary, workflow drift warning, and suggested next action
- `debug` - reproduce and isolate a failure without editing code, then hand the evidence to `fix` or `implement`
- `audit` - branch-aware or full-project review across all concerns or a focused quality, security, performance, or tests lens; `audit independent current` prepares an immutable checkpoint for a fresh reviewer session or configured isolated reviewer child; records findings in `blueprint/context/findings.md` and independent receipts in `blueprint/context/review.md`, where blocking findings or stale review state stop `complete`
- `doctor` - Blueprint health check for setup, adapters, plans, overview freshness, dashboard state, and workflow drift; it may offer to reset only malformed generated dashboard state after approval

### Plan and set up

- `onboard` - tune commands, standards, visibility, ignore rules, and tool adapters after overlaying the Blueprint onto a freshly scaffolded or early project
- `adopt` - bootstrap the Blueprint into an existing brownfield app with shipped features
- `discovery` - optional deep, multi-turn planning conversation that drafts the two user-owned plans only after review and approval; direct plan writing remains fully supported
- `overview` - distill the two planning docs into
  `blueprint/context/project-overview.md`, then offer a reviewed initial planning
  baseline commit before Feature 1
- `prototype` - optional, pre-build static mockups to lock the look
- `tests` - set up unit testing by default, or a repeatable browser harness with `tests browser`
- `ci` - explicitly set up one project-specific Verify command and matching automatic GitHub checks, with an optional local pre-push hook

### Recover and release

- `fix` - document an ad-hoc bug or change into `blueprint/context/current-feature.md`
- `rollback` - plan a safe reversal of a completed feature from its archive and exact git commit, with later-dependency review before code changes
- `release` - optional Render or Vercel deployment readiness, local config, env review, and smoke-test planning

In Codex, invoke these as skills (`$onboard`, `$discovery`, `$overview`, `$feature`,
`$implement`, and so on) or ask naturally, such as "run the overview." In Claude
Code and Google Antigravity, use slash commands such as `/onboard` or `/feature`.
These are AI chat commands, not terminal commands. In OpenCode or other tools
without a dedicated invocation syntax, ask the agent to run the matching skill
or follow its `SKILL.md` manually. The
conventions in `blueprint/context/` apply however a step is invoked. `/discovery`
is never required: users may write detailed plans directly or develop them
through any conversation before running `/overview`.

### Automation

Optional explicit-only skill: `autopilot` combines `feature` or `fix` with
`implement` in one bounded pass when directly invoked, including the configured
regular quality gates. The normal workflow stops for human approval of the spec
before implementation; Autopilot continues through that review point. It may
create checkpoint commits on the feature or fix branch after passing steps and
repair confirmed P0/P1 findings when its audit gate runs. It stops before
`/complete`, merge, push, deploy, or destructive actions.

Optional explicit-only skill: `continuous` can resume or select the next planned
feature and repeat the complete local feature lifecycle through the configured
limit or end of the build plan. It creates one branch and one local main commit
per feature, applies the Continuous quality gates, archives and merges serially,
and stops on decisions or failed safety gates. It never pushes, deploys,
publishes, sends, or performs destructive actions.

Deployment is also explicit. `/release` can prepare local Render or Vercel config
and run readiness checks, but it must stop before deploy, remote service changes,
push, or publish unless the user gives a separate yes in the current chat.

## Dashboard activity

The dashboard can show the active or most recent substantial Blueprint command
from `blueprint/.state/run.json`. This file is generated local state, ignored by
Git, and never part of a feature commit.

Commands with meaningful progress or a durable handoff should write it when the
state directory exists: `onboard`, `adopt`, `discovery`, `overview`, `feature`,
`fix`, `rollback`, `implement`, `debug`, `check`, `audit`, `tests`,
`ci`, `prototype`, `autopilot`, `continuous`, `complete`, and
`release`. Short orientation commands such as `explore`, `brief`, `status`, and `doctor`
do not write activity state. The `check guide` mode also never writes activity
state; select the Check mode before any activity call. Doctor's optional
approved reset removes malformed activity instead of recording another run.

Writing the initial activity record is the first action of a tracked command,
before project inspection, preflight, or other tool calls. This one generated
state write does not authorize product changes or bypass any safety check.

Never create or edit `run.json` directly. From the project root, use the first
helper that exists:

```text
node .agents/skills/doctor/scripts/run-state.mjs <action> <options>
node .claude/skills/doctor/scripts/run-state.mjs <action> <options>
```

Start with `start --command <skill> --summary <truthful-summary> --boundary
<boundary>`. Use `update` at meaningful milestones or for a blocker, with
`--status blocked` and `--resume <exact-command>` when recovery is needed. End
with `finish --status ready|completed --summary <truthful-summary>`. The helper
validates every field before atomically replacing the generated file. If it is
missing or fails, report the activity warning and continue the workflow without
writing a manual fallback.

The helper writes this schema:

```json
{
  "schemaVersion": 1,
  "command": "continuous",
  "status": "running",
  "summary": "Completing the remaining build plan",
  "detail": "Implementing feature 3.",
  "boundary": "local-only",
  "startedAt": "<ISO-8601 timestamp>",
  "updatedAt": "<ISO-8601 timestamp>",
  "resumeCommand": "/continuous resume",
  "progress": { "current": 2, "total": 5, "label": "features" },
  "feature": { "id": "3", "title": "Export reports" }
}
```

`status` must be `running`, `blocked`, `ready`, or `completed`. Use `ready` when
the command reached its intended review handoff, such as Autopilot waiting for
review before `/complete`. Use `blocked` with the exact recovery command when
work can resume. `boundary` must be `read-only`, `reviewed`, or `local-only`.
The progress, feature, detail, boundary, and resume fields are optional. Never
put secrets, raw logs, prompts, or user content in this file. Activity tracking
must not change a command's approval boundaries or turn a reporting failure into
a workflow failure.

## Automatic verification

Automatic GitHub checks are a separate explicit setup. `/onboard` and `/adopt`
only report existing checks and point to `/ci` or `$ci` when none exist. Running
`/ci` inspects the real project and defines one `Verify` command from checks that
already exist. Use this order when available: typecheck, tests, then build. Never
invent a test runner or another check just to fill the command.

For JavaScript and TypeScript projects, prefer a package script such as `verify`
and use the detected package manager. For other stacks, use the native task
runner or exact combined command. Record the exact command under Commands below.

The optional `.github/workflows/verify.yml` must run that same command for pull
requests and pushes to the default branch. Preserve existing workflows, use the
project's real runtime and install command, and grant only `contents: read` by
default. This setup does not add coverage, browser tests, security scans, or
version matrices; those remain later project choices. A local pre-push hook that
runs the same `Verify` command is offered as an opt-in at the end of `/ci`, and
`git push --no-verify` still bypasses it, so the remote ruleset stays the lock.

GitHub branch protection or a ruleset can require the check after the repository
is pushed, but that is a separate remote setting. Missing automatic GitHub
checks do not make the Blueprint unusable.

## Commands

The stack runs in Docker Compose (`db`, `api`, `web`) with Ollama on the host.
`make` targets exist but `make` is not installed on this machine, so the raw
commands are canonical.

- Start the stack: `docker compose up -d --build` (UI http://localhost:3000,
  API http://localhost:8000; `api` runs `alembic upgrade head` on boot)
- Stop: `docker compose down` (add `-v` for a clean database)
- Seed demo data: `docker compose exec api python -m app.scripts.seed_demo`
- Test (backend pytest, against the `buildgate_test` database, fake embedding
  provider, no Ollama needed):
  `docker compose exec -e DATABASE_URL=postgresql+psycopg://buildgate:buildgate@db:5432/buildgate_test api pytest -q`
  Rebuild `api` first if tests or app code changed.
- Migrate manually: `docker compose exec api alembic upgrade head`
- Frontend dev server (outside Docker, from `frontend/`): `npm install`, then
  `npm run dev`
- Frontend build and typecheck (from `frontend/`): `npm run build`
- Logs: `docker compose logs -f api`

A full clean verification is `docker compose down -v && docker compose up -d
--build`, then seed, tests, and a browser click-through. Budget ~20 minutes when
a full board review is part of it.

No lint command is usable yet: `npm run lint` calls `next lint`, but there is no
ESLint config, so it prompts interactively. There are no frontend tests and no
combined Verify command or GitHub checks; run `/ci` when you want them.

Browser testing is also opt-in. Run `/tests browser` or `$tests browser` to add
or normalize a browser harness and document its exact command as `Browser
tests`. Check and Continuous Mode can then reuse it without installing tooling
mid-feature.
