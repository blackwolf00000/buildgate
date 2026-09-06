"""The deterministic decision engine.

Implements `buildgate-decision-engine-spec.md`. The final status is computed by
policy code from structured agent output -- the model never selects it.

`evaluate()` is pure: no clock, no randomness, no database, no network, no
logging. Every input it reads arrives in `DecisionInputs`; every threshold
arrives in `DecisionThresholds`. Identical inputs produce an identical result,
which is what makes the decision reproducible and the audit trail meaningful.

Evaluation is strictly ordered and first match wins:
completeness -> BLOCK -> REVISE -> APPROVE -> fallback. Every rule that matches
is still recorded in `rule_ids`, so a blocker outranked by an earlier stage is
never discarded -- only superseded. `deciding_rule_id` names the one that set
the status.
"""
from dataclasses import dataclass, field

from app.core.enums import (
    AgentStatus,
    AgentType,
    DeadlineAssessment,
    DecisionStatus,
    FindingSeverity,
)


@dataclass(frozen=True)
class AgentReviewInput:
    agent: AgentType
    score: int
    status: AgentStatus
    confidence: float
    critical_information_missing: bool = False
    deadline_assessment: DeadlineAssessment | None = None
    finding_severities: tuple[FindingSeverity, ...] = ()


@dataclass(frozen=True)
class DecisionInputs:
    reviews: tuple[AgentReviewInput, ...]
    expected_agents: frozenset[AgentType]
    deadline_is_fixed: bool


@dataclass(frozen=True)
class DecisionThresholds:
    confidence_floor: float = 0.60
    warning_revise_threshold: int = 3
    approve_min_average_score: int = 75
    approve_min_agent_score: int = 60


@dataclass
class DecisionResult:
    status: DecisionStatus
    review_complete: bool
    deciding_rule_id: str
    rule_ids: list[str] = field(default_factory=list)


# --- Stage 1: completeness -------------------------------------------------

def _completeness_rules(inputs: DecisionInputs) -> list[str]:
    """Structural completeness only: did every expected reviewer come back.

    An agent reporting that *it* lacked information is a judgement about the
    evidence, not about whether the review ran, so C2 lives in stage 3. Keeping
    it here let a reviewer's "I could not tell" outrank another reviewer's
    confident CRITICAL block, which buries the stronger signal.
    """
    fired: list[str] = []
    returned = {r.agent for r in inputs.reviews}
    if not returned >= inputs.expected_agents:
        fired.append("C1_REVIEW_INCOMPLETE")
    return fired


# --- Stage 2: BLOCK --------------------------------------------------------

def _block_rules(inputs: DecisionInputs, t: DecisionThresholds) -> list[str]:
    fired: list[str] = []

    if any(
        r.status is AgentStatus.BLOCK and r.confidence >= t.confidence_floor
        for r in inputs.reviews
    ):
        fired.append("B1_AGENT_BLOCK")

    if any(
        r.confidence >= t.confidence_floor
        and FindingSeverity.CRITICAL in r.finding_severities
        for r in inputs.reviews
    ):
        fired.append("B2_CRITICAL_FINDING")

    if inputs.deadline_is_fixed and _engineering_assessment(inputs) is DeadlineAssessment.INFEASIBLE:
        fired.append("B3_INFEASIBLE_FIXED_DEADLINE")

    return fired


# --- Stage 3: REVISE -------------------------------------------------------

def _revise_rules(inputs: DecisionInputs, t: DecisionThresholds) -> list[str]:
    fired: list[str] = []

    # A BLOCK the agent was not confident about is downgraded, never dropped.
    if any(
        r.status is AgentStatus.BLOCK and r.confidence < t.confidence_floor
        for r in inputs.reviews
    ):
        fired.append("R1_LOW_CONFIDENCE_BLOCK")

    if any(r.status is AgentStatus.FAIL for r in inputs.reviews):
        fired.append("R2_AGENT_FAIL")

    # Moved out of stage 1: an evidence gap must not outrank a confident BLOCK.
    if any(r.critical_information_missing for r in inputs.reviews):
        fired.append("C2_CRITICAL_INFORMATION_MISSING")

    warnings = sum(1 for r in inputs.reviews if r.status is AgentStatus.WARNING)
    if warnings >= t.warning_revise_threshold:
        fired.append("R3_MULTIPLE_WARNINGS")

    if any(FindingSeverity.HIGH in r.finding_severities for r in inputs.reviews):
        fired.append("R4_HIGH_SEVERITY_FINDING")

    # The counterpart to B2, exactly as R1 is the counterpart to B1. Without
    # this a CRITICAL finding from an agent below the confidence floor matches
    # no rule at all and can be approved -- discarding it, which the "never
    # discarded" principle forbids.
    if any(
        r.confidence < t.confidence_floor
        and FindingSeverity.CRITICAL in r.finding_severities
        for r in inputs.reviews
    ):
        fired.append("R7_LOW_CONFIDENCE_CRITICAL_FINDING")

    assessment = _engineering_assessment(inputs)
    if assessment is DeadlineAssessment.INFEASIBLE and not inputs.deadline_is_fixed:
        fired.append("R5_INFEASIBLE_FLEXIBLE_DEADLINE")
    if assessment is DeadlineAssessment.DOUBTFUL and inputs.deadline_is_fixed:
        fired.append("R6_DOUBTFUL_FIXED_DEADLINE")

    return fired


# --- Stage 4: APPROVE ------------------------------------------------------

def _approve_preconditions_met(inputs: DecisionInputs, t: DecisionThresholds) -> bool:
    """Score minimums are APPROVE preconditions, deliberately not REVISE
    triggers -- that is what leaves the fallback reachable."""
    if not inputs.reviews:
        return False
    scores = [r.score for r in inputs.reviews]
    average = sum(scores) / len(scores)
    return average >= t.approve_min_average_score and min(scores) >= t.approve_min_agent_score


def _engineering_assessment(inputs: DecisionInputs) -> DeadlineAssessment | None:
    """deadline_assessment is meaningful only on ENGINEERING."""
    for review in inputs.reviews:
        if review.agent is AgentType.ENGINEERING:
            return review.deadline_assessment
    return None


def evaluate(
    inputs: DecisionInputs, thresholds: DecisionThresholds | None = None
) -> DecisionResult:
    t = thresholds or DecisionThresholds()

    returned = {r.agent for r in inputs.reviews}
    review_complete = returned >= inputs.expected_agents

    completeness = _completeness_rules(inputs)
    blocks = _block_rules(inputs, t)
    revises = _revise_rules(inputs, t)

    # Recorded in evaluation order regardless of which one decides, so a
    # superseded blocker stays visible on the decision and in the audit trail.
    rule_ids = [*completeness, *blocks, *revises]

    if completeness:
        return DecisionResult(
            status=DecisionStatus.REVISE,
            review_complete=review_complete,
            deciding_rule_id=completeness[0],
            rule_ids=rule_ids,
        )

    if blocks:
        return DecisionResult(
            status=DecisionStatus.BLOCKED,
            review_complete=review_complete,
            deciding_rule_id=blocks[0],
            rule_ids=rule_ids,
        )

    if revises:
        return DecisionResult(
            status=DecisionStatus.REVISE,
            review_complete=review_complete,
            deciding_rule_id=revises[0],
            rule_ids=rule_ids,
        )

    if _approve_preconditions_met(inputs, t):
        rule_ids.append("A1_ALL_CLEAR")
        return DecisionResult(
            status=DecisionStatus.APPROVED,
            review_complete=review_complete,
            deciding_rule_id="A1_ALL_CLEAR",
            rule_ids=rule_ids,
        )

    # Mandatory. Without it, "no blocker, no fail, two warnings, average 65"
    # matches nothing at all.
    rule_ids.append("F1_FALLBACK_REVISE")
    return DecisionResult(
        status=DecisionStatus.REVISE,
        review_complete=review_complete,
        deciding_rule_id="F1_FALLBACK_REVISE",
        rule_ids=rule_ids,
    )
