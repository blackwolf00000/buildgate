# AGENTS.md — Resume Notes for BuildGate Phase 1

This file exists so a future session (human or agent) can pick this work
back up without re-deriving context. Read this before touching the code.

## What this is

BuildGate Phase 1 ("Foundation and evidence pipeline") per
`buildgate-phase-plan.md` and `buildgate-core-requirements.md`. No AI/LLM
involved in this phase — it's request intake, document upload, chunking,
local embedding, and semantic retrieval, with the full DB schema for later
phases already in place.

## Status as of this session (2026-09-06)

**All Phase 1 code is written and believed complete.** What's *not* done yet
is end-to-end verification (`docker compose up`, migrations, seeding,
pytest, a UI click-through) — that got interrupted by Docker Desktop/WSL2
instability on this machine (see "Environment quirks" below), and then the
session was paused mid-verification at the user's request.

At the moment this file was written, a `docker compose up --build -d` was
running in the background and had gotten as far as: Postgres/pgvector image
pulled, the `api` image fully built (including the slow `pip install`, which
pulls in `torch`/`sentence-transformers` and takes ~15-17 minutes on a cold
cache), and was exporting the `api` image layer. The `web` (Next.js) image
build and actually starting containers had **not** been confirmed finished.

### To resume verification

```bash
cd D:\Tai-Labs\buildgate
docker compose up --build -d
docker compose ps                 # confirm db/api/web all Running
docker compose exec api alembic upgrade head   # normally auto-runs on api start, but check
make seed                          # or: docker compose exec api python -m app.scripts.seed_demo
make test                          # backend pytest suite
```

Then open http://localhost:3000, click into the seeded request, confirm
documents show `READY`, and try Evidence Search with a query like
`data classification` (should surface the security-policy.md chunk).

Cross-check against the exit criteria checklist in
`buildgate-phase-plan.md` under "Phase 1 — Foundation and evidence
pipeline" — none of those boxes have been ticked yet precisely because
verification didn't finish.

## Environment quirks hit this session (Windows host)

- Docker Desktop and Ollama are installed but were **not** on this shell's
  PATH. Full paths that worked:
  - Docker CLI: `C:\Program Files\Docker\cli-plugins` (varies — also seen at
    `C:\Users\movin\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe`
    depending on which Docker Desktop install/update was active)
  - Docker Desktop app: `C:\Users\movin\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe`
  - Ollama: `C:\Users\movin\AppData\Local\Programs\Ollama\ollama.exe` (its
    server was already running on `localhost:11434`; `nomic-embed-text` was
    pulled successfully during this session)
- Docker Desktop's engine (`dockerDesktopLinuxEngine` named pipe) was flaky —
  `docker info` would sometimes hang on the `Server:` section and fail with
  `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file
  specified`. A `wsl -l -v` check earlier surfaced a
  `Class not registered ... REGDB_E_CLASSNOTREG` error, suggesting a
  WSL2 registration problem on this machine that may intermittently take
  Docker Desktop's backend down with it. The user manually restarted Docker
  Desktop mid-session, after which `docker info` worked reliably. If this
  recurs: restart Docker Desktop from the tray icon (or
  `Start-Process "...\Docker Desktop.exe"` in PowerShell), wait ~30-60s, then
  retry `docker info`.
- Background shell commands (`run_in_background: true`) failed against the
  Docker engine even when a foreground `docker info` in the same session
  succeeded moments before — this turned out to just mean the engine wasn't
  actually up yet (it was flapping), not a background-vs-foreground
  permission issue. Once the engine was genuinely stable, background docker
  commands worked fine (used for the long `docker compose up --build`).
- The heavy step is `pip install -r requirements.txt` inside the `api`
  Docker build (`sentence-transformers` pulls `torch` + CUDA wheels even
  though we run on CPU) — budget 15-20 minutes for a cold build. Consider
  this if a future change touches `backend/requirements.txt`.

## Repository map (Phase 1)

```
buildgate/
├── docker-compose.yml, .env.example, Makefile, README.md
├── docs/DECISIONS.md              — architectural rationale, read this too
├── db/init/01-create-test-db.sql  — creates buildgate_test on first volume init
├── data/demo/*.md                 — 5 seeded demo documents
├── backend/                       — FastAPI app, see app/main.py for routes
│   └── tests/                     — pytest suite, run via `make test`
└── frontend/                      — Next.js App Router UI
```

Full architecture rationale, the embedding-provider fallback design, the
upload-safety approach, and the test-isolation strategy are all written up
in `docs/DECISIONS.md` — that doc plus this file should be enough context to
resume without re-reading every source file.

## Known gaps / things to double check on resume

- [ ] Never confirmed the `web` (Next.js) Docker image builds cleanly
      end-to-end (TypeScript strict-mode compile was reasoned through but not
      actually run).
- [ ] Never confirmed Alembic migration `0001_initial_schema.py` actually
      applies against a real Postgres+pgvector instance (hand-written, not
      autogenerated — check column/enum/index syntax on first run).
- [ ] Never ran `make test` — the pytest suite (`backend/tests/`) has not
      executed once. Pay particular attention to:
      - the `db_session`/`engine` fixtures in `tests/conftest.py` (truncation
        strategy chosen because ingestion runs in its own background-task
        session — see `docs/DECISIONS.md` "Test database strategy")
      - whether `buildgate_test` actually gets created by
        `db/init/01-create-test-db.sql` (only runs on a *fresh* named volume;
        if `buildgate_db_data` already existed from a prior `up`, this script
        won't re-run — `docker compose down -v` first if the test DB is
        missing)
- [ ] Never clicked through the actual UI in a browser.
- [ ] `NEXT_PUBLIC_API_BASE_URL` is baked in at Docker build time, not
      container start (see `docs/DECISIONS.md`) — if the API port/host ever
      changes, the frontend image needs a rebuild, not just a restart.

Once these are checked off and the Phase 1 exit criteria in
`buildgate-phase-plan.md` all pass, follow the phase-boundary rule there
(run tests, run from clean `docker compose up`, update README, record
decisions, commit) before starting Phase 2.
