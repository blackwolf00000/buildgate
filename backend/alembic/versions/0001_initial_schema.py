"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 768

request_status = postgresql.ENUM(
    "DRAFT", "READY_FOR_REVIEW", "REVIEWING", "APPROVED", "REVISE", "BLOCKED", "OVERRIDDEN",
    name="request_status", create_type=False,
)
document_status = postgresql.ENUM(
    "UPLOADED", "PROCESSING", "READY", "PROCESSING_FAILED",
    name="document_status", create_type=False,
)
agent_type = postgresql.ENUM(
    "PRODUCT", "BA", "ARCHITECTURE", "ENGINEERING", "QA", "SECURITY", "USER_EVIDENCE",
    name="agent_type", create_type=False,
)
agent_status = postgresql.ENUM("PASS", "WARNING", "FAIL", "BLOCK", name="agent_status", create_type=False)
deadline_assessment = postgresql.ENUM(
    "FEASIBLE", "DOUBTFUL", "INFEASIBLE", "UNKNOWN", name="deadline_assessment", create_type=False
)
decision_status = postgresql.ENUM("APPROVED", "REVISE", "BLOCKED", name="decision_status", create_type=False)
audit_event_type = postgresql.ENUM(
    "REQUEST_CREATED", "DOCUMENT_UPLOADED", "DOCUMENT_INDEXED", "REVIEW_STARTED",
    "AGENT_REVIEW_COMPLETED", "DECISION_CREATED", "DECISION_ACCEPTED", "REVISION_REQUESTED",
    "DECISION_OVERRIDDEN",
    name="audit_event_type", create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    bind = op.get_bind()
    for enum in (
        request_status, document_status, agent_type, agent_status,
        deadline_assessment, decision_status, audit_event_type,
    ):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("business_reason", sa.Text, nullable=False),
        sa.Column("requested_deadline", sa.Date, nullable=False),
        sa.Column("deadline_is_fixed", sa.Boolean, nullable=False),
        sa.Column("requester", sa.String(200)),
        sa.Column("department", sa.String(200)),
        sa.Column("expected_outcome", sa.Text),
        sa.Column("target_users", sa.Text),
        sa.Column("priority", sa.String(50)),
        sa.Column("notes", sa.Text),
        sa.Column("status", request_status, nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("stored_filename", sa.String(200), nullable=False),
        sa.Column("extension", sa.String(20), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("status", document_status, nullable=False, server_default="UPLOADED"),
        sa.Column("failure_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_documents_request_id", "documents", ["request_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_request_id", "document_chunks", ["request_id"])

    op.create_table(
        "agent_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent", agent_type, nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("status", agent_status, nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("findings", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("questions", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("required_actions", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("assumptions", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("critical_information_missing", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("deadline_assessment", deadline_assessment),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_reviews_review_run_id", "agent_reviews", ["review_run_id"])
    op.create_index("ix_agent_reviews_request_id", "agent_reviews", ["request_id"])

    op.create_table(
        "decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", decision_status, nullable=False),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("review_complete", sa.Boolean, nullable=False),
        sa.Column("rule_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_by", sa.String(200)),
        sa.Column("overridden_at", sa.DateTime(timezone=True)),
        sa.Column("override_reason", sa.Text),
        sa.Column("override_risk_owner", sa.String(200)),
        sa.Column("override_accepted_risks", postgresql.JSONB),
        sa.Column("override_approver_name", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_decisions_review_run_id", "decisions", ["review_run_id"])
    op.create_index("ix_decisions_request_id", "decisions", ["request_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", audit_event_type, nullable=False),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("payload", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("decisions")
    op.drop_table("agent_reviews")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("requests")

    bind = op.get_bind()
    for enum in (
        audit_event_type, decision_status, deadline_assessment,
        agent_status, agent_type, document_status, request_status,
    ):
        enum.drop(bind, checkfirst=True)
