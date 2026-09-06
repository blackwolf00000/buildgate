"""Human accountability actions.

AI recommends; a named human decides, and the record is permanent. Each action
is applied once and only once -- a decision that has already been accepted or
overridden cannot be acted on again, because the audit trail is append-only and
a decision that changed after the fact would not be a record of anything.

Re-running a review is the supported way to get a different outcome: it
allocates a new review_run_id and inserts a new decisions row, leaving this one
intact.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.enums import AuditEventType, DecisionStatus, RequestStatus
from app.db.models import Decision, Request
from app.services.audit import record_event

logger = logging.getLogger("buildgate.decisions")


class DecisionAlreadyResolvedError(Exception):
    """The decision has already been accepted or overridden."""


class OverrideValidationError(Exception):
    """An override was submitted without every required field."""


# Enforced here as well as in the Pydantic schema. The requirement is that an
# override is impossible to submit with a field missing *server-side*, so the
# service must not depend on a particular caller having validated first.
REQUIRED_OVERRIDE_FIELDS = (
    "override_reason",
    "override_risk_owner",
    "override_approver_name",
)


_DECISION_TO_REQUEST_STATUS = {
    DecisionStatus.APPROVED: RequestStatus.APPROVED,
    DecisionStatus.REVISE: RequestStatus.REVISE,
    DecisionStatus.BLOCKED: RequestStatus.BLOCKED,
}


def _guard_unresolved(decision: Decision) -> None:
    if decision.accepted_at is not None:
        raise DecisionAlreadyResolvedError("This decision has already been accepted")
    if decision.overridden_at is not None:
        raise DecisionAlreadyResolvedError("This decision has already been overridden")


def accept_decision(db: Session, decision: Decision, actor: str) -> Decision:
    """Accept the recommendation as it stands. The request takes its status."""
    _guard_unresolved(decision)

    request = db.get(Request, decision.request_id)
    decision.accepted_at = datetime.now(timezone.utc)
    decision.accepted_by = actor
    request.status = _DECISION_TO_REQUEST_STATUS[decision.status]
    db.commit()
    db.refresh(decision)

    record_event(
        db,
        decision.request_id,
        AuditEventType.DECISION_ACCEPTED,
        actor=actor,
        payload={
            "decision_id": str(decision.id),
            "review_run_id": str(decision.review_run_id),
            "status": decision.status.value,
            "policy_version": decision.policy_version,
            "model_name": decision.model_name,
            "rule_ids": decision.rule_ids,
            "review_complete": decision.review_complete,
        },
    )
    logger.info(
        "decision=%s request_id=%s accepted status=%s",
        decision.id,
        decision.request_id,
        decision.status.value,
    )
    return decision


def request_revision(db: Session, decision: Decision, actor: str, note: str | None = None) -> Decision:
    """Send the request back for revision regardless of what was recommended."""
    _guard_unresolved(decision)

    request = db.get(Request, decision.request_id)
    decision.accepted_at = datetime.now(timezone.utc)
    decision.accepted_by = actor
    request.status = RequestStatus.REVISE
    db.commit()
    db.refresh(decision)

    record_event(
        db,
        decision.request_id,
        AuditEventType.REVISION_REQUESTED,
        actor=actor,
        payload={
            "decision_id": str(decision.id),
            "review_run_id": str(decision.review_run_id),
            "recommended_status": decision.status.value,
            "policy_version": decision.policy_version,
            "model_name": decision.model_name,
            "rule_ids": decision.rule_ids,
            "note": (note or "").strip() or None,
        },
    )
    logger.info("decision=%s request_id=%s revision requested", decision.id, decision.request_id)
    return decision


def override_decision(
    db: Session,
    decision: Decision,
    actor: str,
    override_reason: str,
    override_risk_owner: str,
    override_approver_name: str,
    override_accepted_risks: list[str],
) -> Decision:
    """Record a human overriding the recommendation, with accountability.

    Every field is mandatory and re-checked here. An override with a blank risk
    owner or an empty accepted-risks list is not an override with a small gap --
    it is an unaccountable decision, which is the one thing this feature exists
    to prevent.
    """
    _guard_unresolved(decision)

    values = {
        "override_reason": override_reason,
        "override_risk_owner": override_risk_owner,
        "override_approver_name": override_approver_name,
    }
    missing = [name for name in REQUIRED_OVERRIDE_FIELDS if not str(values[name] or "").strip()]

    risks = [str(r).strip() for r in (override_accepted_risks or []) if str(r or "").strip()]
    if not risks:
        missing.append("override_accepted_risks")

    if missing:
        raise OverrideValidationError(
            "Override requires every field: " + ", ".join(sorted(missing))
        )

    request = db.get(Request, decision.request_id)
    decision.overridden_at = datetime.now(timezone.utc)
    decision.override_reason = override_reason.strip()
    decision.override_risk_owner = override_risk_owner.strip()
    decision.override_approver_name = override_approver_name.strip()
    decision.override_accepted_risks = risks
    request.status = RequestStatus.OVERRIDDEN
    db.commit()
    db.refresh(decision)

    record_event(
        db,
        decision.request_id,
        AuditEventType.DECISION_OVERRIDDEN,
        actor=actor,
        payload={
            "decision_id": str(decision.id),
            "review_run_id": str(decision.review_run_id),
            "overridden_status": decision.status.value,
            "override_reason": decision.override_reason,
            "override_risk_owner": decision.override_risk_owner,
            "override_approver_name": decision.override_approver_name,
            "override_accepted_risks": risks,
            "policy_version": decision.policy_version,
            "model_name": decision.model_name,
            "rule_ids": decision.rule_ids,
            "review_complete": decision.review_complete,
        },
    )
    logger.warning(
        "decision=%s request_id=%s OVERRIDDEN by actor recommended=%s risk_owner_recorded=%s",
        decision.id,
        decision.request_id,
        decision.status.value,
        bool(decision.override_risk_owner),
    )
    return decision
