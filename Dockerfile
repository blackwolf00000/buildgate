# BuildGate as a single container, for Hugging Face Spaces.
#
# Spaces give you one container and one port. BuildGate normally runs as three
# (db, api, web) plus Ollama on the host, so everything is folded together here:
# Postgres+pgvector, Ollama, FastAPI and Next.js in one image, with Next.js
# proxying /api through to FastAPI so a single port serves both.
#
# This is a deployment shape, not a rearchitecture -- the application code is
# identical to `main`. Use docker-compose.yml for local work; this file exists
# because Spaces cannot run compose.

# --- Stage 1: build the frontend -------------------------------------------
FROM node:20-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
# Same origin: the browser calls /api on the Space's own URL, and the Next.js
# server rewrites that to FastAPI next door.
ENV NEXT_PUBLIC_API_BASE_URL=""
ENV INTERNAL_API_URL="http://127.0.0.1:8000"
RUN npm run build

# --- Stage 2: the runtime ---------------------------------------------------
# Based on the pgvector image so Postgres and the vector extension are already
# present and correctly configured.
FROM pgvector/pgvector:pg16

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv curl ca-certificates gnupg procps \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# requirements-hf.txt is requirements.txt without sentence-transformers, which
# pulls torch and roughly 2 GB of wheels. That package is only the embedding
# fallback for an unreachable Ollama, and Ollama runs inside this same
# container, so it can never be reached. See that file for the reasoning.
COPY backend/requirements-hf.txt /tmp/requirements.txt
RUN python3 -m pip install --break-system-packages --no-cache-dir \
        -r /tmp/requirements.txt

RUN curl -fsSL https://ollama.com/install.sh | sh

# Bake the models into the image. Free Spaces have ephemeral storage, so a
# runtime pull would re-download ~2.5 GB on every cold start and the first
# review would stall for minutes. Baking trades image size for startup.
ENV OLLAMA_MODELS=/opt/ollama-models
RUN mkdir -p $OLLAMA_MODELS \
    && (ollama serve &) \
    && timeout 60 sh -c 'until curl -sf http://127.0.0.1:11434/api/tags >/dev/null; do sleep 1; done' \
    && ollama pull nomic-embed-text \
    && ollama pull qwen2.5:3b \
    && pkill -f "ollama serve" || true

COPY backend/ /app/backend/
# app/scripts/seed_demo.py reads /data/demo as an absolute path, and
# docker-compose.yml mounts it there too. Keep the same location.
COPY data/ /data/
COPY --from=web /web/.next/standalone /app/web/
COPY --from=web /web/.next/static /app/web/.next/static
COPY --from=web /web/public /app/web/public

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh \
    && mkdir -p /data/uploads /var/run/postgresql \
    && chown -R postgres:postgres /data /var/run/postgresql $OLLAMA_MODELS

ENV PGDATA=/var/lib/postgresql/data \
    DATABASE_URL=postgresql+psycopg://buildgate:buildgate@127.0.0.1:5432/buildgate \
    OLLAMA_HOST=http://127.0.0.1:11434 \
    STORAGE_DIR=/data/uploads \
    LLM_MODEL=qwen2.5:3b \
    LLM_KEEP_ALIVE=30m \
    REVIEW_CONCURRENCY=2 \
    RETRIEVAL_MAX_CHUNKS_PER_AGENT=0 \
    OUTBOUND_ALLOWED_HOSTS=localhost,127.0.0.1 \
    PORT=7860

# Spaces route to 7860 by default; keep app_port in README.md in step with this.
EXPOSE 7860

CMD ["/app/start.sh"]
