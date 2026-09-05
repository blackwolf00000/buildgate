import logging

from sqlalchemy.orm import Session

from app.core.enums import AuditEventType, DocumentStatus
from app.db.models import Document, DocumentChunk
from app.services import storage
from app.services.audit import record_event
from app.services.chunking import chunk_text, normalize
from app.services.embeddings import get_embedding_provider
from app.config import get_settings

logger = logging.getLogger("buildgate.ingestion")


def process_document(db: Session, document_id) -> None:
    """Extract -> normalize -> chunk -> embed -> store.

    Runs as a background task after upload. Never raises: any failure marks
    the document PROCESSING_FAILED with a visible reason and leaves the
    parent request untouched.
    """
    settings = get_settings()
    document = db.get(Document, document_id)
    if document is None:
        return

    request_id = document.request_id
    document.status = DocumentStatus.PROCESSING
    db.commit()

    try:
        raw_text = storage.read_document_text(document.request_id, document.stored_filename)
        text = normalize(raw_text)
        if not text:
            raise ValueError("Document contains no extractable text")

        pieces = chunk_text(text, chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)
        if not pieces:
            raise ValueError("Document produced no chunks")

        provider = get_embedding_provider()
        vectors = provider.embed(pieces)

        for index, (piece, vector) in enumerate(zip(pieces, vectors)):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    request_id=document.request_id,
                    chunk_index=index,
                    content=piece,
                    embedding=vector,
                )
            )

        document.status = DocumentStatus.READY
        document.failure_reason = None
        db.commit()

        record_event(
            db,
            document.request_id,
            AuditEventType.DOCUMENT_INDEXED,
            payload={
                "document_id": str(document.id),
                "status": "success",
                "chunk_count": len(pieces),
                "embedding_provider": provider.name,
            },
        )
    except Exception as exc:  # noqa: BLE001 - must never propagate out of a background task
        logger.exception("Document processing failed for %s", document_id)
        db.rollback()
        document = db.get(Document, document_id)
        if document is not None:
            document.status = DocumentStatus.PROCESSING_FAILED
            document.failure_reason = str(exc)[:500]
            db.commit()

        record_event(
            db,
            request_id,
            AuditEventType.DOCUMENT_INDEXED,
            payload={"document_id": str(document_id), "status": "failed", "reason": str(exc)[:500]},
        )
