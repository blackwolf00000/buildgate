# BuildGate — Three-Phase Development Plan

Companion to `buildgate-core-requirements.md` and
`buildgate-decision-engine-spec.md`.

**Phasing principle:** each phase ends with a runnable application and a
coherent story. Phases are ordered by risk — deterministic, testable work
first; model-dependent, high-variance work last. If time runs out, you stop at
a phase boundary with something defensible rather than mid-way through a
half-built review board.

Effort is given as a proportion of available time, not days. Adjust to your
actual budget.

---

## Phase 1 — Foundation and evidence pipeline

**~25% of available time. No AI involved.**

### Goal

A manager can create a request, attach local documents, and see those documents
chunked, embedded, and retrievable by semantic similarity. Everything runs on
one machine via `docker compose up`.

### Scope

- Monorepo structure, Docker Compose, `.env.example`, Makefile
- FastAPI skeleton, `/health`, `/api/runtime`
- Next.js shell with dashboard and request screens
- PostgreSQL + pgvector, full schema including `deadline_is_fixed`,
  `review_run_id`, `policy_version`, `model_name` on `decisions`
- Request CRUD with validation
- Document upload (`.md`, `.txt`) with extension validation, size cap,
  filename sanitization, generated internal names, path-traversal prevention
- Extraction → normalize → chunk → embed → store in pgvector
- Retrieval function with the small-corpus bypass (below ~60 chunks, return
  everything)
- Single outbound-HTTP wrapper with host allowlist and rejection counter
- Audit events for `REQUEST_CREATED`, `DOCUMENT_UPLOADED`, `DOCUMENT_INDEXED`
- Seeded demo documents in `data/demo/`

### Explicitly out of scope

No agents, no decision engine, no privacy page, no override flow, no PDF or
CSV handling.

### Exit criteria

- [ ] `docker compose up` starts the stack on a clean machine
- [ ] Linux path works — `extra_hosts: ["host.docker.internal:host-gateway"]`
      on the api service, or a documented alternative
- [ ] A request can be created, listed, reopened
- [ ] Demo documents upload, chunk, and embed without error
- [ ] A retrieval query against the demo corpus returns sensible chunks
- [ ] Extraction failure marks `PROCESSING_FAILED` without failing the request
- [ ] Tests pass: request creation, upload validation, chunking, path traversal
- [ ] `README.md` setup instructions verified from scratch

### Main risks

Embedding model availability through Ollama. Resolve this on day one — if the
embedding model doesn't work, fall back to a local sentence-transformers
library rather than discovering the problem in Phase 3.

### If behind

Cut the dashboard aggregate counts. Cut `.csv`/`.json` from the UI accept-list.
Do not cut the schema fields — retrofitting them later touches every layer.

---

## Phase 2 — Governance spine

**~40% of available time. One agent only.**

This is the most important phase. At the end of it you have a complete,
demoable product with a single reviewer. The governance argument — evidence
grounding, deterministic decisions, human accountability — is fully intact.

### Goal

Submit the demo request, run one grounded AI reviewer, get a policy-computed
BLOCK/REVISE/APPROVE, and either accept it or override it with recorded
accountability.

### Scope

**Model layer**
- `LLMProvider` interface, `OllamaProvider` implementation
- Schema-constrained generation via Ollama's `format` parameter, plus Pydantic
  validation after
- `temperature = 0`, fixed seed
- Async job record and polling endpoint — build it now, not later
- Loud failure when Ollama is unreachable; no fallback path exists in the code

**One agent — `PRODUCT`, end to end**
- System prompt including the prompt-injection rule
- Agent-specific retrieval query
- Full common output schema, including `critical_information_missing` and
  `deadline_assessment`
- Persisted `agent_reviews` row tied to a `review_run_id`

**Evidence grounding**
- `evidence_id` validation in code against the chunks retrieved for that call
- Invalid IDs stripped, finding demoted to `evidence_status: MISSING`
- UI resolves a reference to its source chunk text on click

**Decision engine**
- Full implementation per `buildgate-decision-engine-spec.md`
- Pure function, rule IDs recorded, fallback branch present
- Complete test suite against mocked agent output — no Ollama dependency

**Accountability and audit**
- Accept / send for revision / override
- Server-side enforcement of override fields
- Append-only audit trail with the full event set
- Audit view reconstructing a request's history

### Explicitly out of scope

The other six agents. Privacy page. Visual polish.

### Exit criteria

- [ ] `PRODUCT` agent returns schema-valid output on the demo request
- [ ] Every finding's evidence reference opens to real local text
- [ ] A test injecting a fabricated `evidence_id` shows it stripped
- [ ] All truth-table rows in the engine spec pass with mocked input
- [ ] `evaluate()` proven pure — same input, same output across 100 runs
- [ ] Override cannot be submitted with any field missing, tested server-side
- [ ] A failed agent produces an incomplete review that cannot APPROVE
- [ ] Full audit history visible for a completed request

### Main risks

Structured output reliability from the local model. If schema-constrained
generation isn't producing valid JSON consistently, that is a Phase 2 blocker
and must be solved before Phase 3 multiplies the problem by seven. Consider a
larger model or a flatter schema.

Latency. Time a single agent call now. If one call takes 90 seconds, seven will
take ten minutes, and that changes what Phase 3 can look like.

### If behind

Cut the audit *view* but keep audit *writes* — the data matters more than the
screen. Do not cut evidence validation or the decision engine tests; they are
the product.

---

## Phase 3 — Full review board and demo

**~35% of available time. Highest variance, lowest structural risk.**

Everything here is additive. Nothing in Phase 3 can break what Phase 2 proved.

### Goal

Seven differentiated reviewers, a reliable BLOCK on the seeded scenario, and a
demo a stranger can follow in five minutes.

### Scope

**Six remaining agents**
- `BA`, `ARCHITECTURE`, `ENGINEERING`, `QA`, `SECURITY`, `USER_EVIDENCE`
- Distinct retrieval query per agent
- **Fixed finding taxonomy per agent** — an agent may only raise findings from
  its own category list. This is what stops seven paraphrases of the same
  observation, which is the single most likely quality failure.
- Add agents in pairs and check differentiation after each pair. If
  `ARCHITECTURE` and `ENGINEERING` produce the same findings, fix the taxonomy
  before adding more.

**Demo determinism**
- Record one known-good run's agent output to `tests/fixtures/demo_run.json`
- Snapshot test asserting the seeded scenario produces BLOCK
- Verify the expected path is B2 — security score below threshold with a
  CRITICAL finding citing `security-policy.md`. That's the strongest narrative
  because the reason quotes the customer's own policy.

**Privacy page**
- Deployment mode, AI runtime, endpoint, database, uploaded data location
- External AI calls as a *measured* counter from the outbound wrapper, not a
  hardcoded zero
- Anything unmeasurable labelled as configuration state, e.g. "External AI
  Providers: Disabled" rather than a fake network figure

**Polish**
- Review progress screen driven by the real job status
- Loading and error states throughout
- Status and decision badges with consistent semantic styling
- `README.md` demo walkthrough, limitations section stating honestly that there
  is no authentication and `approved_by` is free text

### Exit criteria

- [ ] All seven agents return schema-valid output
- [ ] A reader can identify which agent wrote a finding without the label
- [ ] Seeded scenario produces BLOCK across repeated runs
- [ ] Snapshot test locks the demo outcome
- [ ] Privacy page shows a measured external-call count
- [ ] Full demo runs end to end in under five minutes
- [ ] All Definition of Done items in the original spec checked

### Main risks

Agent homogeneity. A small model given seven similar prompts and the same
context produces seven similar answers, which fails the "multi-perspective
challenge" success criterion directly. The taxonomy constraint is the mitigation
— budget real time for tuning it.

### If behind

Ship five agents rather than seven poorly differentiated ones — drop `QA` and
`ARCHITECTURE`, whose concerns overlap most with `BA` and `ENGINEERING`. Five
agents that clearly disagree demonstrate the concept better than seven that
echo each other. Note the reduction in `docs/DECISIONS.md` as a deliberate
choice.

---

## Phase boundary rule

Do not begin a phase while the previous one is broken. At each boundary:

1. Run the full test suite
2. Run the application from a clean `docker compose up`
3. Update `README.md`
4. Record architectural decisions and assumptions in `docs/DECISIONS.md`
5. Commit

The value of this ordering is that Phase 2 alone is a complete product story.
One reviewer, grounded in real evidence, feeding a deterministic policy engine,
with a recorded human override, demonstrates every claim BuildGate makes.
Phase 3 makes it more convincing; it does not make it valid.
