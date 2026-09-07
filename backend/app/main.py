import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import decisions, documents, health, requests, reviews, runtime

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Review runs are in-process background tasks, so anything still marked in
    # flight at startup was orphaned by a previous process and would otherwise
    # block that request's reviews forever.
    from app.db.session import SessionLocal
    from app.services.review import recover_orphaned_runs

    db = SessionLocal()
    try:
        recover_orphaned_runs(db)
    except Exception:  # noqa: BLE001 - never block startup on cleanup
        logging.getLogger("buildgate").exception("Orphan recovery failed")
    finally:
        db.close()
    yield


app = FastAPI(title="BuildGate API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(runtime.router)
app.include_router(requests.router)
app.include_router(documents.router)
app.include_router(reviews.router)
app.include_router(decisions.router)
