"""Review run orchestration.

Runs are asynchronous from the start. Even one local agent call can take tens of
seconds, and Phase 3 multiplies that by seven, so the API creates a job record
and returns immediately; the UI polls. There is no synchronous path to fall
back to.

A failed agent is recorded as failed. Nothing is substituted for it -- no
placeholder score, no default status -- because the decision engine's
completeness stage depends on being able to tell that an agent did not return.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents import AGENT_REGISTRY, EXPECTED_AGENTS
from app.agents.base import run_agent
from app.config import get_settings
from app.core.enums import (
    AgentRunState,
    AuditEventType,
    RequestStatus,
    ReviewRunStatus,
)
from app.db.models import AgentReview, AgentRun, Request, ReviewRun
from app.services.audit import record_event
from app.services.llm import get_llm_provider

logger = logging.getLogger("buildgate.review")


class ReviewAlreadyRunningError(Exception):
    """A run for this request is already PENDING or RUNNING."""


def start_review(db: Session, request: Request, actor: str = "system") -> ReviewRun:
    """Create the job record and its per-agent rows. Does not run anything."""
    existing = (
        db.query(ReviewRun)
        .filter(
            ReviewRun.request_id == request.id,
            ReviewRun.status.in_([ReviewRunStatus.PENDING, ReviewRunStatus.RUNNING]),
        )
        .first()
    )
    if existing is not None:
        raise ReviewAlreadyRunningError(str(existing.id))

    settings = get_settings()
    provider = get_llm_provider()

    run = ReviewRun(
        request_id=request.id,
        status=ReviewRunStatus.PENDING,
        model_name=provider.model,
        policy_version=settings.policy_version,
    )
    db.add(run)
    db.flush()

    for agent in sorted(EXPECTED_AGENTS, key=lambda a: a.value):
        db.add(
            AgentRun(
                review_run_id=run.id,
                request_id=request.id,
                agent=agent,
                state=AgentRunState.PENDING,
            )
        )

    request.status = RequestStatus.REVIEWING
    db.commit()
    db.refresh(run)

    record_event(
        db,
        request.id,
        AuditEventType.REVIEW_STARTED,
        actor=actor,
        payload={
            "review_run_id": str(run.id),
            "model_name": run.model_name,
            "policy_version": run.policy_version,
            "agents": [a.value for a in sorted(EXPECTED_AGENTS, key=lambda x: x.value)],
        },
    )
    return run


def execute_review(db: Session, review_run_id) -> None:
    """Run every agent in the job. Never raises out of the background task."""
    run = db.get(ReviewRun, review_run_id)
    if run is None:
        return

    request = db.get(Request, run.request_id)
    if request is None:
        return

    settings = get_settings()
    provider = get_llm_provider()

    run.status = ReviewRunStatus.RUNNING
    db.commit()

    for agent_run in sorted(run.agent_runs, key=lambda r: r.agent.value):
        spec = AGENT_REGISTRY.get(agent_run.agent)
        if spec is None:
            agent_run.state = AgentRunState.FAILED
            agent_run.error_class = "UnknownAgent"
            db.commit()
            continue

        agent_run.state = AgentRunState.RUNNING
        db.commit()

        try:
            result = run_agent(
                db, request, spec, provider, max_attempts=settings.llm_max_attempts
            )
        except Exception as exc:  # noqa: BLE001 - a failed agent must not kill the run
            # Log the error class only. Never the prompt, the documents, or the
            # model output.
            logger.warning(
                "agent=%s request_id=%s failed error_class=%s",
                agent_run.agent.value,
                request.id,
                type(exc).__name__,
            )
            db.rollback()
            agent_run = db.get(AgentRun, agent_run.id)
            agent_run.state = AgentRunState.FAILED
            agent_run.error_class = type(exc).__name__
            db.commit()
            continue

        output = result.output
        db.add(
            AgentReview(
                review_run_id=run.id,
                request_id=request.id,
                agent=output.agent,
                score=output.score,
                status=output.status,
                confidence=output.confidence,
                summary=output.summary,
                findings=[f.model_dump(mode="json") for f in result.findings],
                questions=output.questions,
                required_actions=output.required_actions,
                assumptions=output.assumptions,
                critical_information_missing=output.critical_information_missing,
                deadline_assessment=output.deadline_assessment,
            )
        )
        agent_run.state = AgentRunState.COMPLETE
        agent_run.latency_ms = result.latency_ms
        agent_run.attempts = result.attempts
        db.commit()

        record_event(
            db,
            request.id,
            AuditEventType.AGENT_REVIEW_COMPLETED,
            payload={
                "review_run_id": str(run.id),
                "agent": output.agent.value,
                "status": output.status.value,
                "score": output.score,
                "confidence": float(output.confidence),
                "latency_ms": result.latency_ms,
                "model_name": run.model_name,
                "evidence_ids_available": len(result.evidence_ids_available),
                "findings_missing_evidence": sum(
                    1 for f in result.findings if f.evidence_status.value == "MISSING"
                ),
            },
        )

    _finalize(db, run)


def _finalize(db: Session, run: ReviewRun) -> None:
    """Close out the run. The decision is computed separately.

    NOTE (Phase 2, in progress): the decision engine is specified in
    buildgate-decision-engine-spec.md and wires in here -- evaluate() over the
    agent_reviews rows for this run, then a `decisions` row and a
    DECISION_CREATED audit event. Until that lands the run completes and the
    request is left in REVIEWING.
    """
    db.refresh(run)
    failed = [r for r in run.agent_runs if r.state is AgentRunState.FAILED]

    run.status = ReviewRunStatus.COMPLETE
    run.completed_at = datetime.now(timezone.utc)
    if failed:
        run.error = f"{len(failed)} agent(s) failed: " + ", ".join(
            f"{r.agent.value}={r.error_class}" for r in failed
        )
    db.commit()

    logger.info(
        "review_run=%s request_id=%s complete failed_agents=%d",
        run.id,
        run.request_id,
        len(failed),
    )


def review_is_complete(run: ReviewRun) -> bool:
    """True when every expected agent returned. Drives the engine's stage 1."""
    completed = {r.agent for r in run.agent_runs if r.state is AgentRunState.COMPLETE}
    return completed >= set(EXPECTED_AGENTS)
