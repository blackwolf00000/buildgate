# Build Plan

Adopted from the existing codebase. Checked items are already shipped on `main`
(Phases 1-3 of `buildgate-phase-plan.md`); unchecked items are the roadmap.

Run `/feature` to spec the next unchecked item, or `/feature 18` to pick one.
Keep completed items checked and append new features as the project grows.
Do not renumber completed features; their archived specs refer to those IDs.

## Your features

### Shipped - Phase 1, foundation and evidence pipeline

- [x] 1. **Stack foundation** - Docker Compose (db, api, web), FastAPI with `/health` and `/api/runtime`, Next.js shell, full Postgres + pgvector schema via Alembic
- [x] 2. **Request intake** - create, list, and reopen structured requests with validation, including `deadline_is_fixed`
- [x] 3. **Safe document upload** - `.md`/`.txt` only, size cap, sanitized filenames, generated internal names, path-traversal prevention
- [x] 4. **Local ingestion pipeline** - extract, normalize, chunk, embed locally, store in pgvector; `PROCESSING_FAILED` without failing the request; visible sentence-transformers fallback
- [x] 5. **Evidence retrieval and search** - per-query retrieval with the small-corpus bypass, plus the evidence search box in the UI
- [x] 6. **Outbound HTTP wrapper** - single allowlisted client with allowed and rejected counters
- [x] 7. **Seeded demo data** - demo request and five documents in `data/demo/` via `seed_demo`

### Shipped - Phase 2, governance spine

- [x] 8. **Async review runs** - job record, `202` trigger, polling endpoint, per-agent progress persisted as results arrive, orphaned-run recovery on startup
- [x] 9. **PRODUCT reviewer end to end** - Ollama provider, JSON Schema `format`, Pydantic validation, temp 0 with seed offset per retry, prompt-injection rule
- [x] 10. **Evidence grounding** - code validation of every `evidence_id`, fabricated ids stripped and findings demoted to `MISSING`, references open to source text
- [x] 11. **Deterministic decision engine** - pure `evaluate()` per the engine spec, strict rule order with fallback, configurable thresholds, rule ids recorded
- [x] 12. **Human accountability** - accept, send for revision, override with all fields enforced server-side; decisions resolve once
- [x] 13. **Audit trail** - append-only event set and an audit view that reconstructs a request's history
- [x] 14. **Review, decision, and evidence UI** - review board, decision panel with rules fired, inline evidence references

### Shipped - Phase 3, full review board

- [x] 15. **Six remaining reviewers** - BA, ARCHITECTURE, ENGINEERING, QA, SECURITY, USER_EVIDENCE with distinct retrieval queries and schema-enforced finding taxonomies
- [x] 16. **Review latency tuning** - batched retrieval, model `keep_alive` and release, per-agent chunk cap, pinned `num_ctx`, optional concurrency (off by default)
- [x] 17. **Single-container Hugging Face image** - root `Dockerfile` and `start.sh` folding the stack into one Space (authored, not yet built; see 21)

### Roadmap

- [x] 18. **Reliable demo BLOCK** - re-run the full board and get the seeded scenario to BLOCK via `B2` (SECURITY CRITICAL citing `security-policy.md`) across repeated runs, or record why not
- [ ] 19. **Demo snapshot test** - record a known-good run to `tests/fixtures/demo_run.json` and add a test locking the demo outcome
- [ ] 20. **Demo polish and README refresh** - loading and error states throughout, consistent badges, README demo walkthrough for the seven-agent board, honest limitations section
- [ ] 21. **Verify the Hugging Face image** - build and boot the single-container image and confirm seed, review, and decision work end to end
- [ ] 22. **Demo timing** - bring the full demo under five minutes, or revise the target in the phase plan with measured numbers
