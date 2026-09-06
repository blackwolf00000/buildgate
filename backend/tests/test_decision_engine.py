"""Truth table for the decision engine.

Every row in buildgate-decision-engine-spec.md, with mocked agent output and no
Ollama dependency. These tests are the product argument: the final status is
computed by policy code, not chosen by a model, so it must be provable.
"""
import pytest

from app.core.enums import (
    AgentStatus,
    AgentType,
    DeadlineAssessment,
    DecisionStatus,
    FindingSeverity,
)
from app.services.decision_engine import (
    AgentReviewInput,
    DecisionInputs,
    DecisionThresholds,
    evaluate,
)

T = DecisionThresholds()

# A single-agent board keeps most rows readable; rows that need several agents
# build their own tuple.
PRODUCT_ONLY = frozenset({AgentType.PRODUCT})
FULL_BOARD = frozenset({AgentType.PRODUCT, AgentType.ENGINEERING, AgentType.QA})


def review(
    agent=AgentType.PRODUCT,
    score=85,
    status=AgentStatus.PASS,
    confidence=0.9,
    critical_information_missing=False,
    deadline_assessment=None,
    severities=(),
):
    return AgentReviewInput(
        agent=agent,
        score=score,
        status=status,
        confidence=confidence,
        critical_information_missing=critical_information_missing,
        deadline_assessment=deadline_assessment,
        finding_severities=tuple(severities),
    )


def inputs(reviews, expected=PRODUCT_ONLY, deadline_is_fixed=False):
    return DecisionInputs(
        reviews=tuple(reviews),
        expected_agents=expected,
        deadline_is_fixed=deadline_is_fixed,
    )


# --- Row 1-2: completeness -------------------------------------------------

def test_row1_missing_agent_is_incomplete():
    result = evaluate(inputs([review()], expected=FULL_BOARD))
    assert result.status is DecisionStatus.REVISE
    assert result.deciding_rule_id == "C1_REVIEW_INCOMPLETE"
    assert result.review_complete is False


def test_row2_critical_information_missing():
    result = evaluate(inputs([review(critical_information_missing=True)]))
    assert result.status is DecisionStatus.REVISE
    assert result.deciding_rule_id == "C2_CRITICAL_INFORMATION_MISSING"
    assert result.review_complete is True


# --- Row 3-6: BLOCK --------------------------------------------------------

def test_row3_confident_block():
    result = evaluate(inputs([review(status=AgentStatus.BLOCK, confidence=0.90)]))
    assert result.status is DecisionStatus.BLOCKED
    assert result.deciding_rule_id == "B1_AGENT_BLOCK"


def test_row4_block_exactly_at_confidence_floor_is_binding():
    result = evaluate(inputs([review(status=AgentStatus.BLOCK, confidence=0.60)]))
    assert result.status is DecisionStatus.BLOCKED
    assert result.deciding_rule_id == "B1_AGENT_BLOCK"


def test_row5_critical_finding_blocks_even_when_agent_only_warns():
    result = evaluate(
        inputs(
            [
                review(
                    status=AgentStatus.WARNING,
                    confidence=0.80,
                    severities=(FindingSeverity.CRITICAL,),
                )
            ]
        )
    )
    assert result.status is DecisionStatus.BLOCKED
    assert result.deciding_rule_id == "B2_CRITICAL_FINDING"


def test_row6_infeasible_against_a_fixed_deadline_blocks():
    result = evaluate(
        inputs(
            [review(agent=AgentType.ENGINEERING, deadline_assessment=DeadlineAssessment.INFEASIBLE)],
            expected=frozenset({AgentType.ENGINEERING}),
            deadline_is_fixed=True,
        )
    )
    assert result.status is DecisionStatus.BLOCKED
    assert result.deciding_rule_id == "B3_INFEASIBLE_FIXED_DEADLINE"


# --- Row 7-12: REVISE ------------------------------------------------------

def test_row7_block_below_confidence_floor_downgrades_but_is_not_discarded():
    result = evaluate(inputs([review(status=AgentStatus.BLOCK, confidence=0.59)]))
    assert result.status is DecisionStatus.REVISE
    assert result.deciding_rule_id == "R1_LOW_CONFIDENCE_BLOCK"
    # the requirement is explicit that it is never discarded
    assert "R1_LOW_CONFIDENCE_BLOCK" in result.rule_ids


def test_row8_agent_fail():
    result = evaluate(inputs([review(status=AgentStatus.FAIL)]))
    assert result.status is DecisionStatus.REVISE
    assert result.deciding_rule_id == "R2_AGENT_FAIL"


def test_row9_three_warnings():
    board = frozenset({AgentType.PRODUCT, AgentType.QA, AgentType.SECURITY})
    result = evaluate(
        inputs(
            [
                review(agent=AgentType.PRODUCT, status=AgentStatus.WARNING, score=80),
                review(agent=AgentType.QA, status=AgentStatus.WARNING, score=80),
                review(agent=AgentType.SECURITY, status=AgentStatus.WARNING, score=80),
            ],
            expected=board,
        )
    )
    assert result.status is DecisionStatus.REVISE
    assert result.deciding_rule_id == "R3_MULTIPLE_WARNINGS"


def test_row10_high_severity_finding():
    result = evaluate(inputs([review(severities=(FindingSeverity.HIGH,))]))
    assert result.status is DecisionStatus.REVISE
    assert result.deciding_rule_id == "R4_HIGH_SEVERITY_FINDING"


def test_row11_infeasible_against_a_flexible_deadline_revises():
    result = evaluate(
        inputs(
            [review(agent=AgentType.ENGINEERING, deadline_assessment=DeadlineAssessment.INFEASIBLE)],
            expected=frozenset({AgentType.ENGINEERING}),
            deadline_is_fixed=False,
        )
    )
    assert result.status is DecisionStatus.REVISE
    assert result.deciding_rule_id == "R5_INFEASIBLE_FLEXIBLE_DEADLINE"


def test_row12_doubtful_against_a_fixed_deadline_revises():
    result = evaluate(
        inputs(
            [review(agent=AgentType.ENGINEERING, deadline_assessment=DeadlineAssessment.DOUBTFUL)],
            expected=frozenset({AgentType.ENGINEERING}),
            deadline_is_fixed=True,
        )
    )
    assert result.status is DecisionStatus.REVISE
    assert result.deciding_rule_id == "R6_DOUBTFUL_FIXED_DEADLINE"


# --- Row 13-14, 17: APPROVE ------------------------------------------------

def test_row13_doubtful_against_a_flexible_deadline_is_tolerated():
    result = evaluate(
        inputs(
            [
                review(
                    agent=AgentType.ENGINEERING,
                    deadline_assessment=DeadlineAssessment.DOUBTFUL,
                    score=85,
                )
            ],
            expected=frozenset({AgentType.ENGINEERING}),
            deadline_is_fixed=False,
        )
    )
    assert result.status is DecisionStatus.APPROVED
    assert result.deciding_rule_id == "A1_ALL_CLEAR"


def test_row14_all_clear_approves():
    result = evaluate(inputs([review(score=85)]))
    assert result.status is DecisionStatus.APPROVED
    assert result.deciding_rule_id == "A1_ALL_CLEAR"


def test_row17_two_warnings_with_good_scores_still_approves():
    board = frozenset({AgentType.PRODUCT, AgentType.QA})
    result = evaluate(
        inputs(
            [
                review(agent=AgentType.PRODUCT, status=AgentStatus.WARNING, score=86),
                review(agent=AgentType.QA, status=AgentStatus.WARNING, score=70),
            ],
            expected=board,
        )
    )
    assert result.status is DecisionStatus.APPROVED
    assert result.deciding_rule_id == "A1_ALL_CLEAR"


# --- Row 15-16: the fallback -----------------------------------------------

def test_row15_one_agent_below_the_score_floor_falls_through():
    board = frozenset({AgentType.PRODUCT, AgentType.QA})
    result = evaluate(
        inputs(
            [
                review(agent=AgentType.PRODUCT, score=115 - 30),  # 85
                review(agent=AgentType.QA, score=55),
            ],
            expected=board,
        )
    )
    # average 70 and min 55 both fail the APPROVE preconditions, and no REVISE
    # rule matches -- this is exactly what the fallback exists for
    assert result.status is DecisionStatus.REVISE
    assert result.deciding_rule_id == "F1_FALLBACK_REVISE"


def test_row16_the_case_the_requirements_name_explicitly():
    """no blocker, no fail, two warnings, average 65 -> matches no rule."""
    board = frozenset({AgentType.PRODUCT, AgentType.QA})
    result = evaluate(
        inputs(
            [
                review(agent=AgentType.PRODUCT, status=AgentStatus.WARNING, score=65),
                review(agent=AgentType.QA, status=AgentStatus.WARNING, score=65),
            ],
            expected=board,
        )
    )
    assert result.status is DecisionStatus.REVISE
    assert result.deciding_rule_id == "F1_FALLBACK_REVISE"
    # nothing else fired -- proving the fallback is load-bearing, not decorative
    assert result.rule_ids == ["F1_FALLBACK_REVISE"]


# --- Row 18: the documented ordering question ------------------------------

def test_row18_incompleteness_outranks_a_binding_block_but_records_it():
    result = evaluate(
        inputs(
            [review(status=AgentStatus.BLOCK, confidence=0.95)],
            expected=FULL_BOARD,
        )
    )
    assert result.status is DecisionStatus.REVISE
    assert result.deciding_rule_id == "C1_REVIEW_INCOMPLETE"
    # superseded, never discarded -- the blocker is still on the record
    assert "B1_AGENT_BLOCK" in result.rule_ids


# --- Required properties ---------------------------------------------------

def test_evaluate_is_pure_across_repeated_calls():
    payload = inputs(
        [review(status=AgentStatus.WARNING, score=70, severities=(FindingSeverity.MEDIUM,))]
    )
    first = evaluate(payload)
    for _ in range(100):
        again = evaluate(payload)
        assert again.status is first.status
        assert again.deciding_rule_id == first.deciding_rule_id
        assert again.rule_ids == first.rule_ids


@pytest.mark.parametrize("score", [0, 40, 75, 99, 100])
@pytest.mark.parametrize("severity", [FindingSeverity.INFO, FindingSeverity.LOW])
def test_a_failed_agent_can_never_approve(score, severity):
    board = frozenset({AgentType.PRODUCT, AgentType.QA})
    result = evaluate(
        inputs(
            [
                review(agent=AgentType.PRODUCT, score=score, severities=(severity,)),
                review(agent=AgentType.QA, status=AgentStatus.FAIL, score=score),
            ],
            expected=board,
        )
    )
    assert result.status is not DecisionStatus.APPROVED


def test_an_incomplete_review_can_never_approve():
    result = evaluate(inputs([review(score=100)], expected=FULL_BOARD))
    assert result.status is not DecisionStatus.APPROVED
    assert result.review_complete is False


def test_thresholds_come_from_configuration_not_constants():
    payload = inputs([review(status=AgentStatus.BLOCK, confidence=0.50)])

    # default floor 0.60 -> 0.50 is below it, so the block downgrades
    assert evaluate(payload).deciding_rule_id == "R1_LOW_CONFIDENCE_BLOCK"

    # lower the floor and the same input becomes a binding block
    lenient = DecisionThresholds(confidence_floor=0.40)
    assert evaluate(payload, lenient).deciding_rule_id == "B1_AGENT_BLOCK"


def test_warning_threshold_is_configurable():
    board = frozenset({AgentType.PRODUCT, AgentType.QA})
    payload = inputs(
        [
            review(agent=AgentType.PRODUCT, status=AgentStatus.WARNING, score=85),
            review(agent=AgentType.QA, status=AgentStatus.WARNING, score=85),
        ],
        expected=board,
    )
    # two warnings is under the default threshold of 3
    assert evaluate(payload).status is DecisionStatus.APPROVED
    strict = DecisionThresholds(warning_revise_threshold=2)
    assert evaluate(payload, strict).deciding_rule_id == "R3_MULTIPLE_WARNINGS"


def test_deadline_assessment_is_ignored_on_non_engineering_agents():
    # PRODUCT volunteering INFEASIBLE must not reach the engine's deadline rules
    result = evaluate(
        inputs(
            [review(agent=AgentType.PRODUCT, deadline_assessment=DeadlineAssessment.INFEASIBLE)],
            deadline_is_fixed=True,
        )
    )
    assert result.status is DecisionStatus.APPROVED


# --- regression: a CRITICAL finding must never be discarded ----------------

def test_low_confidence_critical_finding_downgrades_rather_than_disappearing():
    """Regression. B2 is gated on the confidence floor, so a CRITICAL finding
    from an unconfident agent used to match no rule at all and be APPROVED --
    discarded, which the "never discarded" principle forbids. R7 is B2's
    counterpart exactly as R1 is B1's."""
    result = evaluate(
        inputs(
            [
                review(
                    status=AgentStatus.WARNING,
                    confidence=0.50,
                    score=85,
                    severities=(FindingSeverity.CRITICAL,),
                )
            ]
        )
    )
    assert result.status is DecisionStatus.REVISE
    assert result.deciding_rule_id == "R7_LOW_CONFIDENCE_CRITICAL_FINDING"
    assert "R7_LOW_CONFIDENCE_CRITICAL_FINDING" in result.rule_ids


def test_confident_critical_finding_still_blocks():
    """R7 must not steal cases that belong to B2."""
    result = evaluate(
        inputs(
            [
                review(
                    status=AgentStatus.WARNING,
                    confidence=0.90,
                    severities=(FindingSeverity.CRITICAL,),
                )
            ]
        )
    )
    assert result.status is DecisionStatus.BLOCKED
    assert result.deciding_rule_id == "B2_CRITICAL_FINDING"


@pytest.mark.parametrize("confidence", [0.0, 0.3, 0.59, 0.6, 0.9, 1.0])
def test_a_critical_finding_can_never_be_approved_at_any_confidence(confidence):
    """The property the regression above is a specific instance of."""
    result = evaluate(
        inputs([review(confidence=confidence, score=100, severities=(FindingSeverity.CRITICAL,))])
    )
    assert result.status is not DecisionStatus.APPROVED
