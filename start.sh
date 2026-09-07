#!/usr/bin/env bash
# Boots the whole stack inside one container, in dependency order:
# Postgres -> Ollama -> migrations -> seed -> FastAPI -> Next.js.
#
# Next.js runs in the foreground and owns PID 1's fate: if it exits, the
# container exits, which is what Spaces expects.
set -euo pipefail

log() { echo "[start] $*"; }

# --- Postgres ---------------------------------------------------------------
# Storage on a free Space is ephemeral, so the cluster is initialised on every
# cold start. That is fine: the demo data is seeded below and nothing here is a
# system of record.
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  log "initialising postgres cluster"
  mkdir -p "$PGDATA" && chown -R postgres:postgres "$PGDATA"
  su postgres -c "initdb -D $PGDATA --username=buildgate --auth=trust" >/dev/null
fi

log "starting postgres"
su postgres -c "pg_ctl -D $PGDATA -o '-c listen_addresses=127.0.0.1 -p 5432' -w -t 60 start"

su postgres -c "psql -h 127.0.0.1 -U buildgate -d postgres -tc \
  \"SELECT 1 FROM pg_database WHERE datname='buildgate'\"" | grep -q 1 \
  || su postgres -c "createdb -h 127.0.0.1 -U buildgate buildgate"
su postgres -c "psql -h 127.0.0.1 -U buildgate -d postgres -tc \
  \"SELECT 1 FROM pg_database WHERE datname='buildgate_test'\"" | grep -q 1 \
  || su postgres -c "createdb -h 127.0.0.1 -U buildgate buildgate_test"
su postgres -c "psql -h 127.0.0.1 -U buildgate -d buildgate \
  -c 'CREATE EXTENSION IF NOT EXISTS vector'" >/dev/null

# --- Ollama -----------------------------------------------------------------
log "starting ollama"
su postgres -c "OLLAMA_MODELS=$OLLAMA_MODELS OLLAMA_HOST=127.0.0.1:11434 \
  OLLAMA_KEEP_ALIVE=${LLM_KEEP_ALIVE:-30m} \
  OLLAMA_NUM_PARALLEL=${REVIEW_CONCURRENCY:-2} ollama serve" &

for _ in $(seq 1 60); do
  curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
  sleep 1
done
curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1 \
  && log "ollama up: $(curl -s http://127.0.0.1:11434/api/tags | head -c 120)" \
  || log "WARNING: ollama did not come up; reviews will fail loudly, by design"

# --- Schema and demo data ---------------------------------------------------
cd /app/backend
log "applying migrations"
alembic upgrade head

log "seeding demo data"
python3 -m app.scripts.seed_demo || log "seed skipped (already present or failed)"

# --- FastAPI ----------------------------------------------------------------
log "starting api on 8000"
uvicorn app.main:app --host 127.0.0.1 --port 8000 &

for _ in $(seq 1 60); do
  curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1 && break
  sleep 1
done
log "api health: $(curl -s http://127.0.0.1:8000/health || echo unreachable)"

# --- Next.js ----------------------------------------------------------------
# Foreground. Its /api/* rewrite proxies to the API above, so the single
# published port serves both the UI and the API.
log "starting web on ${PORT:-7860}"
cd /app/web
exec env PORT="${PORT:-7860}" HOSTNAME=0.0.0.0 \
  INTERNAL_API_URL=http://127.0.0.1:8000 node server.js
