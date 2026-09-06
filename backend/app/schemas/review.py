import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.enums import EvidenceStatus


class AgentRunOut(BaseModel):
    agent: str
    state: str
    error_class: str | None
    latency_ms: int | None
    attempts: int

    class Config:
        from_attributes = True


class FindingOut(BaseModel):
    severity: str
    title: str
    description: str
    evidence_ids: list[str] = []
    stripped_evidence_ids: list[str] = []
    evidence_status: EvidenceStatus = EvidenceStatus.OK


class AgentReviewOut(BaseModel):
    id: uuid.UUID
    agent: str
    score: int
    status: str
    confidence: float
    summary: str
    findings: list[FindingOut] = []
    questions: list[str] = []
    required_actions: list[str] = []
    assumptions: list[str] = []
    critical_information_missing: bool
    deadline_assessment: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewRunOut(BaseModel):
    """What the UI polls while a run is in flight."""

    id: uuid.UUID
    request_id: uuid.UUID
    status: str
    model_name: str
    policy_version: str
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    agent_runs: list[AgentRunOut] = []
    reviews: list[AgentReviewOut] = []

    class Config:
        from_attributes = True


class EvidenceChunkResolved(BaseModel):
    """A single evidence reference resolved back to its source text."""

    evidence_id: str
    document_id: uuid.UUID
    document_filename: str
    chunk_index: int
    content: str
