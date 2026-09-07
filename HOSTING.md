# Hosting BuildGate on Vercel (free plan)

This branch (`hosting`) adds a self-contained demo deployment. It exists so the
product can be shown from a URL in a couple of minutes, with no Docker, no
database and no local model.

**Read the honesty section before showing this to anyone.** The hosted demo is
deliberately not the product, and it says so on screen.

## Why the real thing cannot run here

`buildgate-core-requirements.md` opens with a non-negotiable constraint: *"All
inference runs locally through Ollama. No cloud model, ever, including as a
fallback."* Vercel's free plan is incompatible with the architecture that
follows from it:

| Requirement | Vercel free |
|---|---|
| Ollama for every inference call | cannot run; no persistent process, no GPU |
| ~100s per agent, ~12 min per board | Hobby functions time out in 10s |
| Background job outliving the HTTP response | serverless functions end with the response |
| Postgres + pgvector | not included; needs an external service |
| `sentence-transformers` (torch, ~5 GB) | 250 MB function limit |
| Uploads written to disk | filesystem is ephemeral and read-only |

Making a live review work on Vercel would mean calling a hosted model API,
which is the one thing the product promises never to do. So this branch does
not do that.

## What the hosted demo actually is

The Next.js app serves the whole thing. `frontend/app/api/**` implements the
same HTTP contract the FastAPI backend does, so the UI is unchanged.

**Real, captured from an actual run** (`frontend/lib/demo-data.json`):

- the seeded request and all five demo documents
- all ten evidence chunks, verbatim
- six agent reviews produced by `qwen2.5:3b` on a local machine — every score,
  status, confidence, summary and finding is as the model returned it
- the evidence ids each finding cited, including which ones failed validation

**Computed live, not recorded:**

- the decision. `frontend/lib/decisionEngine.ts` is a faithful port of
  `backend/app/services/decision_engine.py` — same rule ids, same stage order,
  same first-match-wins semantics — and it runs on every request. A canned
  decision would demo nothing, since "the status is computed by policy code,
  not chosen by a model" is the product's central claim.
- the override checks. Every field mandatory, blank treated as missing,
  accepted risks explicitly ticked, one resolution per decision (409 after).

**Simulated:**

- the passage of time during a run. Agents complete on a timer so the polling
  UI behaves as it does for real, compressed to ~42s instead of ~12 minutes.

**Downgraded, and labelled in the UI:**

- evidence search is keyword matching. There is no embedding model here, so it
  is not semantic retrieval and does not claim to be.

**Not present:**

- any model. Nothing is generated at request time.
- `ENGINEERING`. The captured run had seven agents and that one failed schema
  validation, so the recording has six. The board therefore shows six
  reviewers, which is what actually happened rather than a tidied-up version.
- persistence. Run state is in server memory, per instance, and resets when the
  instance idles. Fine for a demo; not a storage layer.

## Deploying

1. Push this branch and import the repo at [vercel.com/new](https://vercel.com/new).
2. Set **Root Directory** to `frontend`. Vercel then detects Next.js on its own.
3. Add one environment variable:

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | *(empty string)* |

   Empty means "same origin", so the UI calls the bundled route handlers.
   Leaving it unset makes the browser call `http://localhost:8000` and the
   demo will appear broken.
4. Deploy. No other configuration, no database, no secrets.

## Running the demo locally

```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE_URL= npm run dev
```

Or through the existing image, which needs nothing else running:

```bash
docker compose build web
docker run --rm -p 3100:3000 -e NEXT_PUBLIC_API_BASE_URL= buildgate-web:latest
```

## The two-minute walkthrough

1. Open the request. Five documents, all `READY`.
2. Press **Run review**. Reviewers move `PENDING` → `RUNNING` → `COMPLETE` over
   about 40 seconds, driven by real polling.
3. Read the findings. They differ by reviewer — SECURITY on policy, QA on prior
   defects, ARCHITECTURE on coupling — which is the multi-perspective claim.
4. Click the evidence reference on SECURITY's CRITICAL finding. It opens the
   actual text of `security-policy.md`: the mandatory Data Governance sign-off
   this request would bypass.
5. Note the findings badged **evidence missing**. Those are real: the model
   cited ids that did not resolve, and the grounding check stripped them. This
   is the control working, not a defect.
6. The decision reads **BLOCKED**, deciding rule `B2_CRITICAL_FINDING`, with
   every rule that fired listed beneath it.
7. Try **Override** with a field blank. The server refuses it. Fill all of
   them and it records the risk owner and approver, and the audit trail
   reconstructs the whole history.

## Keeping the port honest

`decisionEngine.ts` and `decision_engine.py` must agree. The Python side is the
authority and carries the truth-table tests
(`backend/tests/test_decision_engine.py`, 20 rows plus the purity and threshold
properties). If you change a rule, change both — there is currently no test
asserting the two implementations agree, which is the first thing worth adding
if this branch outlives the demo.
