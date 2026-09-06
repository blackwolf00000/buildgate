import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.requests import _get_request_or_404
from app.db.models import AgentReview, DocumentChunk, Document, ReviewRun
from app.db.session import SessionLocal, get_db
from app.schemas.review import AgentReviewOut, EvidenceChunkResolved, ReviewRunOut
from app.services.evidence import EVIDENCE_ID_PATTERN
from app.services.retrieval import evidence_id_for
from app.services.review import ReviewAlreadyRunningError, execute_review, start_review

router = APIRouter(prefix="/api")


def _run_review(review_run_id) -> None:
    """Background entrypoint. Opens its own session -- the request-scoped one
    is already torn down by the time this runs."""
    db = SessionLocal()
    try:
        execute_review(db, review_run_id)
    finally:
        db.close()


def _serialize(db: Session, run: ReviewRun) -> ReviewRunOut:
    reviews = (
        db.query(AgentReview)
        .filter(AgentReview.review_run_id == run.id)
        .order_by(AgentReview.created_at)
        .all()
    )
    payload = ReviewRunOut.model_validate(run, from_attributes=True)
    payload.reviews = [
        AgentReviewOut.model_validate(r, from_attributes=True) for r in reviews
    ]
    return payload


@router.post("/requests/{request_id}/review", response_model=ReviewRunOut, status_code=202)
def trigger_review(
    request_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Start a review run and return immediately. The UI polls the run."""
    request = _get_request_or_404(db, request_id)

    try:
        run = start_review(db, request)
    except ReviewAlreadyRunningError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"A review run is already in progress for this request ({exc})",
        ) from exc

    background_tasks.add_task(_run_review, run.id)
    return _serialize(db, run)


@router.get("/reviews/{review_run_id}", response_model=ReviewRunOut)
def get_review_run(review_run_id: uuid.UUID, db: Session = Depends(get_db)):
    run = db.get(ReviewRun, review_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Review run not found")
    return _serialize(db, run)


@router.get("/requests/{request_id}/reviews", response_model=list[ReviewRunOut])
def list_review_runs(request_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_request_or_404(db, request_id)
    runs = (
        db.query(ReviewRun)
        .filter(ReviewRun.request_id == request_id)
        .order_by(ReviewRun.created_at.desc())
        .all()
    )
    return [_serialize(db, run) for run in runs]


@router.get(
    "/requests/{request_id}/evidence/{evidence_id}",
    response_model=EvidenceChunkResolved,
)
def resolve_evidence(
    request_id: uuid.UUID, evidence_id: str, db: Session = Depends(get_db)
):
    """Resolve an evidence reference to its source chunk text.

    Scoped to the request, so an evidence id belonging to another request's
    documents will not resolve here.
    """
    _get_request_or_404(db, request_id)

    match = EVIDENCE_ID_PATTERN.match(evidence_id)
    if match is None:
        raise HTTPException(status_code=400, detail="Malformed evidence id")

    try:
        document_id = uuid.UUID(match.group("document_id"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Malformed evidence id") from exc
    chunk_index = int(match.group("chunk_index"))

    row = (
        db.query(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(
            DocumentChunk.request_id == request_id,
            DocumentChunk.document_id == document_id,
            DocumentChunk.chunk_index == chunk_index,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Evidence not found for this request")

    chunk, document = row
    return EvidenceChunkResolved(
        evidence_id=evidence_id_for(chunk.document_id, chunk.chunk_index),
        document_id=document.id,
        document_filename=document.original_filename,
        chunk_index=chunk.chunk_index,
        content=chunk.content,
    )
