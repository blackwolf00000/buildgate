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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents import AGENT_REGISTRY, EXPECTED_AGENTS
from app.agents.base import (
    collect_evidence_for_all,
    execute_agent_call,
    prepare_agent_call,
)
from app.config import get_settings
from app.core.enums import (
    AgentRunState,
    AuditEventType,
    FindingSeverity,
    RequestStatus,
    ReviewRunStatus,
)
from app.services.decision_engine import (
    AgentReviewInput,
    DecisionInputs,
    DecisionThresholds,
    evaluate,
)
from app.db.models import (
    AgentReview,
    AgentRun,
    Decision,
    DocumentChunk,
    Request,
    ReviewRun,
)
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

    # One embedding pass for the whole board before any generation, so Ollama
    # swaps between the embedding model and the review model once rather than
    # once per agent. If retrieval fails the run cannot proceed at all, so this
    # is deliberately outside the per-agent try/except.
    ordered = sorted(run.agent_runs, key=lambda r: r.agent.value)
    specs = [AGENT_REGISTRY[r.agent] for r in ordered if r.agent in AGENT_REGISTRY]
    # Retrieval uses the embedding model; a previous run may still be holding
    # the review model resident via keep_alive, and on a constrained host both
    # will not fit. Release it before embedding.
    release = getattr(provider, "release", None)
    if callable(release):
        release()
    try:
        evidence_by_agent = collect_evidence_for_all(db, request.id, specs)
    except Exception as exc:  # noqa: BLE001 - surfaced on the run, not swallowed
        logger.warning(
            "review_run=%s retrieval failed error_class=%s", run.id, type(exc).__name__
        )
        db.rollback()
        run = db.get(ReviewRun, review_run_id)
        run.status = ReviewRunStatus.FAILED
        run.error = f"Evidence retrieval failed: {type(exc).__name__}"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return

    # Prepare every call on this thread: prompts are built from ORM objects, and
    # the concurrent phase must not touch the session.
    calls = {}
    for agent_run in ordered:
        spec = AGENT_REGISTRY.get(agent_run.agent)
        if spec is None:
            agent_run.state = AgentRunState.FAILED
            agent_run.error_class = "UnknownAgent"
            continue
        evidence = evidence_by_agent.get(agent_run.agent)
        if evidence is None:
            agent_run.state = AgentRunState.FAILED
            agent_run.error_class = "NoEvidence"
            continue
        calls[agent_run.agent] = prepare_agent_call(request, spec, evidence)
    db.commit()

    runnable = [r for r in ordered if r.agent in calls]
    by_agent = {r.agent: r for r in runnable}
    workers = max(1, min(settings.review_concurrency, len(runnable)))

    def _call(agent):
        try:
            return agent, execute_agent_call(
                calls[agent], provider, max_attempts=settings.llm_max_attempts
            ), None
        except Exception as exc:  # noqa: BLE001 - a failed agent must not kill the run
            return agent, None, exc

    def _persist(agent, result, exc) -> None:
        """Write one agent's outcome. Always on this thread, never in a worker."""
        agent_run = by_agent[agent]
        if exc is not None:
            # Log the error class only. Never the prompt, documents, or output.
            logger.warning(
                "agent=%s request_id=%s failed error_class=%s",
                agent.value, request.id, type(exc).__name__,
            )
            agent_run.state = AgentRunState.FAILED
            agent_run.error_class = type(exc).__name__
            db.commit()
            return

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

    # Each outcome is persisted as soon as it arrives, so the polling UI shows
    # real progress rather than nothing until the whole board finishes.
    if workers > 1:
        for agent_run in runnable:
            agent_run.state = AgentRunState.RUNNING
        db.commit()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_call, r.agent) for r in runnable]
            for future in as_completed(futures):
                _persist(*future.result())
    else:
        for agent_run in runnable:
            agent_run.state = AgentRunState.RUNNING
            db.commit()
            _persist(*_call(agent_run.agent))

    _finalize(db, run, request)


def _thresholds() -> DecisionThresholds:
    """Thresholds always come from configuration, never inline constants."""
    settings = get_settings()
    return DecisionThresholds(
        confidence_floor=settings.confidence_floor,
        warning_revise_threshold=settings.warning_revise_threshold,
        approve_min_average_score=settings.approve_min_average_score,
        approve_min_agent_score=settings.approve_min_agent_score,
    )


def _decision_inputs(db: Session, run: ReviewRun, request: Request) -> DecisionInputs:
    """Project the persisted agent_reviews rows into the engine's pure inputs."""
    rows = db.query(AgentReview).filter(AgentReview.review_run_id == run.id).all()

    reviews = []
    for row in rows:
        severities = []
        for finding in row.findings or []:
            try:
                severities.append(FindingSeverity(finding["severity"]))
            except (KeyError, ValueError, TypeError):
                continue
        reviews.append(
            AgentReviewInput(
                agent=row.agent,
                score=row.score,
                status=row.status,
                confidence=float(row.confidence),
                critical_information_missing=row.critical_information_missing,
                deadline_assessment=row.deadline_assessment,
                finding_severities=tuple(severities),
            )
        )

    return DecisionInputs(
        reviews=tuple(reviews),
        expected_agents=EXPECTED_AGENTS,
        deadline_is_fixed=request.deadline_is_fixed,
    )


def _finalize(db: Session, run: ReviewRun, request: Request) -> Decision:
    """Close the run and compute its decision.

    The request is deliberately left in REVIEWING. The decision is a
    *recommendation* until a named human accepts or overrides it -- that is
    Feature 5's whole point -- so only those actions move the request's status.
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

    result = evaluate(_decision_inputs(db, run, request), _thresholds())

    decision = Decision(
        review_run_id=run.id,
        request_id=request.id,
        status=result.status,
        policy_version=run.policy_version,
        model_name=run.model_name,
        review_complete=result.review_complete,
        rule_ids=result.rule_ids,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)

    # Enough to explain the outcome without reading source: which rules fired,
    # which one decided, the policy and model behind it, and what evidence was
    # on the table. References only -- never document or prompt content.
    document_ids = [
        str(document_id)
        for (document_id,) in db.query(DocumentChunk.document_id)
        .filter(DocumentChunk.request_id == request.id)
        .distinct()
        .all()
    ]
    record_event(
        db,
        request.id,
        AuditEventType.DECISION_CREATED,
        payload={
            "review_run_id": str(run.id),
            "decision_id": str(decision.id),
            "status": result.status.value,
            "deciding_rule_id": result.deciding_rule_id,
            "rule_ids": result.rule_ids,
            "review_complete": result.review_complete,
            "policy_version": run.policy_version,
            "model_name": run.model_name,
            "failed_agents": [r.agent.value for r in failed],
            "document_ids": document_ids,
        },
    )

    logger.info(
        "review_run=%s request_id=%s complete failed_agents=%d decision=%s rule=%s",
        run.id,
        run.request_id,
        len(failed),
        result.status.value,
        result.deciding_rule_id,
    )
    return decision


def review_is_complete(run: ReviewRun) -> bool:
    """True when every expected agent returned. Drives the engine's stage 1."""
    completed = {r.agent for r in run.agent_runs if r.state is AgentRunState.COMPLETE}
    return completed >= set(EXPECTED_AGENTS)


def recover_orphaned_runs(db: Session) -> int:
    """Fail any run left in flight by a process that is no longer running.

    Review runs execute as in-process background tasks, so an API restart --
    a deploy, a crash, a `docker compose up --build` -- leaves the run row
    PENDING or RUNNING with nothing driving it. Because `start_review` refuses
    to start a second run while one is in flight, a single orphan blocks every
    future review of that request permanently.

    Called once on startup. Anything still in flight at that moment cannot
    belong to this process, so it is safe to close out.
    """
    orphans = (
        db.query(ReviewRun)
        .filter(ReviewRun.status.in_([ReviewRunStatus.PENDING, ReviewRunStatus.RUNNING]))
        .all()
    )
    for run in orphans:
        for agent_run in run.agent_runs:
            if agent_run.state in (AgentRunState.PENDING, AgentRunState.RUNNING):
                agent_run.state = AgentRunState.FAILED
                agent_run.error_class = "RunInterrupted"
        run.status = ReviewRunStatus.FAILED
        run.error = "Interrupted: the API restarted while this run was in flight"
        run.completed_at = datetime.now(timezone.utc)

    if orphans:
        db.commit()
        logger.warning("Recovered %d orphaned review run(s) on startup", len(orphans))
    return len(orphans)
