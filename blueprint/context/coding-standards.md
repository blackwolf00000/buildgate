# Coding Standards

> Adopted from the conventions the BuildGate code already follows. The
> load-bearing invariants (model never picks the status, grounding is a code
> control, no cloud fallback) live in `AGENTS.md` and override anything here.
> The *why* behind most choices is in `docs/DECISIONS.md`.

## Project structure

- `backend/` - FastAPI app (`app/`), Alembic migrations (`alembic/versions/`),
  pytest suite (`tests/`).
  - `app/api/` - thin routers, one per resource (`requests`, `documents`,
    `reviews`, `decisions`, `runtime`, `health`), prefixed `/api/...`.
  - `app/services/` - all business logic: ingestion, chunking, embeddings,
    retrieval, llm, evidence, review, decision engine, decisions, audit,
    storage, outbound http client.
  - `app/agents/` - one module per reviewer plus shared `base.py`; every agent
    is registered in `app/agents/__init__.py`.
  - `app/schemas/` - Pydantic request/response and agent-output models.
  - `app/db/` - SQLAlchemy models and session; `app/core/enums.py` for shared
    enums; `app/config.py` for every tunable.
- `frontend/` - Next.js App Router: `app/` for routes, flat `components/`,
  `lib/api.ts` for the typed API client.
- `data/demo/` - seeded demo documents. `db/init/` - first-boot SQL.

## Python (backend)

- Python 3.11, type hints throughout, `X | None` style.
- Routers stay thin: parse, call a service, map domain errors to
  `HTTPException`. Logic and invariants belong in `app/services/`.
- Services raise specific domain exceptions (`UploadValidationError`,
  `OverrideValidationError`, `DecisionAlreadyResolvedError`,
  `LLMUnavailableError`, ...). Routers translate them to status codes (409 for
  already-resolved, 4xx for validation).
- Validate input with Pydantic schemas, and re-check rules that must hold
  server-side in the service layer too (the override fields are enforced in
  both). Blank counts as missing.
- Every threshold, model name, size limit, and timing knob lives in
  `Settings` in `app/config.py`, overridable from `.env`. No inline constants
  for policy values.
- `decision_engine.evaluate()` stays pure: no clock, randomness, database, or
  I/O.
- All outbound HTTP goes through `app/services/http_client.py`. Never call
  `httpx` directly for an external host.
- Record significant state changes with `services/audit.record_event`. Audit is
  append-only; never update or delete audit rows.
- Logging uses `logging.getLogger("buildgate.<area>")`. Log ids, agent type,
  status, latency, model, and error class; never full documents, prompts,
  tokens, or secrets.

## Database and migrations

- SQLAlchemy 2 models in `app/db/models.py`; schema changes ship as a new
  numbered Alembic revision in `backend/alembic/versions/`.
- New postgres enums in a migration need `create_type=False`.
- The test suite uses `create_all()` and does not exercise migrations. Verify a
  migration by booting `api` against a fresh volume (`docker compose down -v`).
- Re-runs insert new rows (`review_run_id`, `decisions`); never overwrite
  history.

## AI calls

- One model, one provider (`OllamaProvider`). Schema-constrained via Ollama's
  `format`, then validated with Pydantic. Prompt rules are not controls; code
  checks are.
- `temperature = 0`, fixed seed offset by attempt number, pinned `num_ctx`.
- Agent finding categories are schema enums. A new agent gets its own taxonomy,
  retrieval query, and role framing, and must not share categories with others
  (except `INJECTION_ATTEMPT`).
- Retrieved document text is evidence only; instructions inside documents are
  never followed.

## TypeScript and React (frontend)

- TypeScript strict mode; no `any`. API types are declared once in
  `frontend/lib/api.ts` and mirror the backend schemas, including string-union
  status types.
- Functional components only. Pages and interactive components are client
  components (`"use client"`) that fetch through the `api` object in
  `lib/api.ts`, holding `loading` / `error` / data state with `useState` and
  `useEffect`. There are no Server Actions or server-side data fetching.
- The API base URL comes from `NEXT_PUBLIC_API_BASE_URL` (baked in at build
  time). Under Hugging Face Spaces, `/api/*` is rewritten to FastAPI when
  `INTERNAL_API_URL` is set.
- Imports use the `@/` alias.
- The UI accept-list for uploads must match what the backend implements.

## Naming

- Python: modules and functions `snake_case`, classes `PascalCase`, enums and
  audit event types `SCREAMING_SNAKE_CASE`.
- Components: PascalCase files and exports (`DecisionPanel.tsx`).
- TypeScript functions camelCase; types and interfaces PascalCase, no prefix.
- Rule ids follow the engine spec (`B2_CRITICAL_FINDING`, `R3_...`).

## Styling

- Tailwind CSS 3 with `tailwind.config.ts`; utility classes inline in JSX.
- Light UI in the slate palette. Semantic status colours are centralised in
  `StatusBadge`; reuse it rather than restyling statuses ad hoc.
- No inline `style` attributes.

> TODO (confirm): no component library is in use; keep it that way unless a
> polish feature decides otherwise.

## Error handling

- Backend: fail loudly. An unreachable Ollama on review raises, never degrades
  silently. A failed agent is recorded as failed; nothing is substituted.
- Document extraction failures mark the document `PROCESSING_FAILED` with a
  visible reason without failing the request.
- Frontend: `lib/api.ts` throws `Error("<status>: <detail>")` on non-2xx; pages
  catch it into an `error` state and render it.

## Testing

**Status: a backend test gate exists.** `AGENTS.md` declares a `Test` command
(pytest inside the `api` container against `buildgate_test`). Logic-bearing
backend steps must ship passing tests in the same diff, and the suite must be
green before a step is approved and before `/complete` merges. There are no
frontend tests and no browser harness; frontend steps ride on the build plus
browser evidence.

The opt-in switch is one signal: a `test` command in the Commands section of
`AGENTS.md`. When `AGENTS.md` declares a `Verify` command it becomes the
umbrella gate (typecheck, tests, then build); there is none yet, and `/ci` owns
creating it.

- **What to test:** pure and server-side logic where a wrong answer is
  possible: decision rules and truth-table rows, evidence validation, schema
  validation, upload and path safety, chunking, accountability enforcement,
  review-run state.
- **What not to test:** UI components and live-model behaviour. Tests must not
  require Ollama; use the fake deterministic embedding provider and mocked agent
  output from `tests/conftest.py`.
- Tests live in `backend/tests/test_<area>.py`, not next to source.
- Rebuild the `api` image before running tests after code or test edits, or the
  container runs stale copies.
- An empty suite should fail, not pass.

## Browser Verification

For UI and integration behavior, prefer real browser evidence over reading the
code and assuming it works.

- Browser automation is separately opt-in through `/tests browser`. No
  `Browser tests` command is declared yet.
- Until one is, use the running stack (http://localhost:3000), screenshots, API
  output, and the build instead. Do not add a runner silently mid-feature.
- A full board review takes many minutes on the local host; plan browser checks
  of review flows around that, or use a seeded or recorded run.

## Code Quality

- No commented-out code unless specified
- No unused imports or variables
- Keep functions under 50 lines when possible

## Comments

Write code that explains itself; comment only what the code cannot say.
Over-commenting is a common AI tell, so resist it.

- Comment the **why**, not the **what**. Delete any comment that restates the code.
- No banner/header blocks, section dividers, or step-by-step narration of obvious
  code. A file does not need a comment announcing each region.
- A comment earns its place only when it captures something the code can't: a
  non-obvious decision, a gotcha or workaround, why a value is what it is, or a
  link to a spec or issue. This codebase uses such comments for measured values
  (for example the `num_ctx` and chunk-cap settings); keep that habit.
- Prefer self-documenting names and small functions over explanatory comments.
- Keep doc comments minimal: a one-line purpose on an exported type or function is
  plenty; don't write JSDoc that just repeats the signature.
- When in doubt, leave the comment out.

## Writing

- No em dashes (U+2014) in generated content: docs, comments, commit messages,
  READMEs, specs. They read as AI-generated.
- Use a hyphen for `term - description` separators; rephrase prose with commas,
  parentheses, or a colon. Avoid en dashes and the ellipsis character too.
- Record measured numbers rather than hoped-for ones, and say plainly when
  something is unverified.
