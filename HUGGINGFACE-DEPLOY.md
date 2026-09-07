# Deploying BuildGate to Hugging Face Spaces (Docker)

This runs the **real** product — live Ollama, real pgvector retrieval, the full
seven-agent board — for free. Unlike the `hosting` branch's Vercel demo,
nothing is recorded or simulated.

Free Spaces give **2 vCPU and 16 GB RAM**, which is more than double the memory
of the 7.4 GB laptop this was developed on. Memory has been the binding
constraint throughout, so this should be a meaningful improvement — though
2 vCPU is fewer cores than the laptop's 16, so verify rather than assume
(see *Measuring* below).

---

## The constraint that shapes everything

**A Space is one container with one published port.** BuildGate normally runs
as three containers plus Ollama on the host. So this branch folds the whole
stack into a single image:

```
    ┌──────────────── one container ────────────────┐
    │  Next.js  :7860  ──/api/*──►  FastAPI  :8000  │   ← only 7860 is published
    │                                   │           │
    │                    Postgres+pgvector :5432    │
    │                    Ollama            :11434   │
    └───────────────────────────────────────────────┘
```

Next.js proxies `/api/*` to FastAPI via a rewrite, so one port serves both.
Application code is **unchanged** from `main` — this is a deployment shape, not
a rearchitecture.

---

## What you get, and what you give up

**Real:** live model inference, real embeddings and vector retrieval, the
actual decision engine, working override enforcement, the full audit trail.

**Given up on the free tier:**

- **Storage is ephemeral.** The Postgres cluster is re-initialised and re-seeded
  on every cold start. Requests you create, documents you upload and overrides
  you record are lost when the Space sleeps. Fine for a demo; not a system of
  record. (Persistent storage is a paid add-on.)
- **Spaces sleep** after ~48h of inactivity. The next visit pays a cold start.
- **Free Spaces are public.** BuildGate has **no authentication** — anyone with
  the URL can create requests and record overrides. Make the Space private if
  that matters (private Spaces are available on the free tier).
- **2 vCPU.** Reviews will take minutes, not seconds. Set expectations before
  demoing live.

The models are baked into the image rather than pulled at runtime, precisely
because storage is ephemeral — a runtime pull would re-download ~2.5 GB on
every cold start and stall the first review.

---

## Deploying

### 1. Create the Space

[huggingface.co/new-space](https://huggingface.co/new-space)

| Setting | Value |
|---|---|
| SDK | **Docker** → *Blank* |
| Hardware | CPU basic (free) |
| Visibility | Private, unless you want it world-readable |

### 2. Push this branch to it

```bash
git remote add space https://huggingface.co/spaces/<your-username>/<space-name>
git push space huggingface:main
```

Spaces build from the `main` branch of the Space repo, so the local
`huggingface` branch is pushed to `main` there.

You will be asked for a token — create one at
[huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) with
**write** access.

### 3. Watch the build

The Space's **Logs** tab shows the build. Expect **20–40 minutes** on the first
run: `pip install` and baking two Ollama models dominate. Later pushes reuse
cached layers unless `requirements.txt` or the frontend changes.

### 4. Confirm it started

The **Logs** tab should show, in order:

```
[start] initialising postgres cluster
[start] starting postgres
[start] starting ollama
[start] ollama up: {"models":[...
[start] applying migrations
[start] seeding demo data
[start] starting api on 8000
[start] api health: {"status":"ok"}
[start] starting web on 7860
```

Then open the Space. `/api/runtime` should report
`"ollama":{"reachable":true}` and `"active_provider":"ollama"`. If it says
`sentence-transformers`, Ollama did not start — check the logs for the
WARNING line.

---

## Measuring, before you trust it

The laptop's problem was diagnosed by prefill throughput, not wall-clock. Do
the same here. In the Space's terminal, or by hitting the API:

```bash
curl -s http://127.0.0.1:11434/api/generate -d '{
  "model":"qwen2.5:3b","prompt":"Write two sentences about databases.",
  "stream":false,"options":{"num_ctx":8192}}' | python3 -c '
import json,sys; d=json.load(sys.stdin); ns=1e9
print(f"prefill {d[\"prompt_eval_count\"]/(d[\"prompt_eval_duration\"]/ns):.0f} tok/s")
print(f"gen     {d[\"eval_count\"]/(d[\"eval_duration\"]/ns):.0f} tok/s")'
```

**Prefill tok/s is the number that matters.** On the laptop it was ~40, against
100–300 for a healthy machine, because memory starvation forced constant
paging. With 16 GB and a 2 GB model there should be no paging at all — if
prefill is still under 60, the limit is the 2 vCPU rather than memory, and the
honest response is to drop to a smaller model or cut the board rather than keep
tuning.

Tunable via Space **Settings → Variables** without rebuilding:

| Variable | Default here | Notes |
|---|---|---|
| `LLM_MODEL` | `qwen2.5:3b` | only models baked into the image are available |
| `REVIEW_CONCURRENCY` | `2` | matched to 2 vCPU; raising it past core count will not help |
| `RETRIEVAL_MAX_CHUNKS_PER_AGENT` | `0` | 0 passes the whole small corpus, as the requirements specify |
| `LLM_NUM_CTX` | `3072` | prompts measure ~2000 tokens |

---

## Running the same image locally

Worth doing before pushing, since a Space build is slow to iterate on:

```bash
docker build -t buildgate-hf .
docker run --rm -p 7860:7860 buildgate-hf
```

Then open `http://localhost:7860`. This is byte-for-byte what the Space runs.

---

## Troubleshooting

**Build times out or runs out of space.** The image is large (~6–8 GB), mostly
torch and the baked models. If the build fails on size, drop
`sentence-transformers` from `requirements.txt` for this branch — it is only
the *embedding fallback*, and Ollama is in the same container here, so it can
never be reached. That saves roughly 2 GB.

**`/api/runtime` says `active_provider: sentence-transformers`.** Ollama is not
running. Check the logs for the WARNING. Review calls will fail loudly rather
than silently degrade, which is intended.

**The UI loads but every request fails.** The `/api` rewrite is not active.
`INTERNAL_API_URL` must be set at **build** time for the rewrite to be
registered, and `NEXT_PUBLIC_API_BASE_URL` must be empty so the browser calls
the Space's own origin. Both are set in the Dockerfile.

**Everything is gone after a restart.** Expected — storage is ephemeral. The
demo data re-seeds automatically; anything you created by hand does not.

**Reviews take minutes.** Also expected on 2 vCPU. See *Measuring* above, and
consider a smaller board for live demos.
