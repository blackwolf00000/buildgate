import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.enums import DocumentStatus


class DocumentOut(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID
    original_filename: str
    extension: str
    size_bytes: int
    status: DocumentStatus
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EvidenceChunkOut(BaseModel):
    evidence_id: str
    document_id: str
    document_filename: str
    chunk_index: int
    content: str
    score: float | None = None
