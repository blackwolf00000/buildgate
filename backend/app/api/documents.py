import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.enums import AuditEventType
from app.db.models import Document
from app.db.session import SessionLocal, get_db
from app.schemas.document import DocumentOut, EvidenceChunkOut
from app.services.audit import record_event
from app.services.embeddings import get_embedding_provider
from app.services.ingestion import process_document
from app.services.retrieval import evidence_id_for, retrieve
from app.services.storage import UploadValidationError, save_upload

from app.api.requests import _get_request_or_404

router = APIRouter(prefix="/api/requests")


def _run_ingestion(document_id):
    db = SessionLocal()
    try:
        process_document(db, document_id)
    finally:
        db.close()


@router.post("/{request_id}/documents", response_model=DocumentOut, status_code=201)
def upload_document(
    request_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    db: Session = Depends(get_db),
):
    req = _get_request_or_404(db, request_id)
    raw_bytes = file.file.read()

    try:
        original_filename, stored_filename, extension, size_bytes = save_upload(
            str(req.id), file, raw_bytes
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    document = Document(
        request_id=req.id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        extension=extension,
        size_bytes=size_bytes,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    record_event(
        db,
        req.id,
        AuditEventType.DOCUMENT_UPLOADED,
        payload={"document_id": str(document.id), "filename": original_filename},
    )

    background_tasks.add_task(_run_ingestion, document.id)

    return document


@router.get("/{request_id}/documents", response_model=list[DocumentOut])
def list_documents(request_id: str, db: Session = Depends(get_db)):
    req = _get_request_or_404(db, request_id)
    return db.query(Document).filter(Document.request_id == req.id).order_by(Document.created_at).all()


@router.get("/{request_id}/documents/{document_id}", response_model=DocumentOut)
def get_document(request_id: str, document_id: str, db: Session = Depends(get_db)):
    req = _get_request_or_404(db, request_id)
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Document not found")
    doc = db.get(Document, doc_uuid)
    if doc is None or doc.request_id != req.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{request_id}/evidence-search", response_model=list[EvidenceChunkOut])
def evidence_search(
    request_id: str,
    q: str = Query(min_length=1),
    db: Session = Depends(get_db),
):
    req = _get_request_or_404(db, request_id)
    provider = get_embedding_provider()
    [query_embedding] = provider.embed([q])

    results = retrieve(db, req.id, query_embedding)

    return [
        EvidenceChunkOut(
            evidence_id=evidence_id_for(chunk.document_id, chunk.chunk_index),
            document_id=str(chunk.document_id),
            document_filename=doc.original_filename,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            score=score,
        )
        for chunk, doc, score in results
    ]
