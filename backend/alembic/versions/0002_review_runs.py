"""review run job records

Adds the async job tables the review board is driven from.

Note the `create_type=False` on both new enums. Without it `op.create_table`
re-emits CREATE TYPE via SQLAlchemy's before_create hook after the explicit
create() below has already made the type, which is what broke 0001 on every
boot. Keep this pattern for any future migration that declares a postgres enum.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

review_run_status = postgresql.ENUM(
    "PENDING", "RUNNING", "COMPLETE", "FAILED",
    name="review_run_status", create_type=False,
)
agent_run_state = postgresql.ENUM(
    "PENDING", "RUNNING", "COMPLETE", "FAILED",
    name="agent_run_state", create_type=False,
)

# Declared in 0001; referenced here without being re-created.
agent_type = postgresql.ENUM(
    "PRODUCT", "BA", "ARCHITECTURE", "ENGINEERING", "QA", "SECURITY", "USER_EVIDENCE",
    name="agent_type", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (review_run_status, agent_run_state):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "review_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", review_run_status, nullable=False, server_default="PENDING"),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_review_runs_request_id", "review_runs", ["request_id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "review_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("review_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent", agent_type, nullable=False),
        sa.Column("state", agent_run_state, nullable=False, server_default="PENDING"),
        sa.Column("error_class", sa.String(200)),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_runs_review_run_id", "agent_runs", ["review_run_id"])
    op.create_index("ix_agent_runs_request_id", "agent_runs", ["request_id"])


def downgrade() -> None:
    op.drop_table("agent_runs")
    op.drop_table("review_runs")

    bind = op.get_bind()
    for enum in (agent_run_state, review_run_status):
        enum.drop(bind, checkfirst=True)
