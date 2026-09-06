"""Review run orchestration: job records, agent failure handling, prompting."""
import io

import pytest

from app.agents import AGENT_REGISTRY, EXPECTED_AGENTS
from app.agents.base import PROMPT_INJECTION_RULE
from app.core.enums import (
    AgentRunState,
    AgentType,
    DeadlineAssessment,
    RequestStatus,
    ReviewRunStatus,
)
from app.db.models import AgentReview, Request, ReviewRun
from app.services.llm import LLMInvalidOutputError, LLMUnavailableError
from app.services.review import (
    ReviewAlreadyRunningError,
    execute_review,
    review_is_complete,
    start_review,
)
from tests.conftest import VALID_REQUEST_PAYLOAD, valid_agent_payload


def _request_with_evidence(client, db_session):
    """Create a request with one ingested document, and return the ORM row."""
    created = client.post("/api/requests", json=VALID_REQUEST_PAYLOAD).json()
    files = {
        "file": (
            "policy.md",
            io.BytesIO(
                b"# Security Policy\n\nAll customer-account fields are tagged "
                b"public-export, customer-visible, or internal-only. Any export "
                b"must pass a field-level classification review before launch."
            ),
            "text/markdown",
        )
    }
    resp = client.post(f"/api/requests/{created['id']}/documents", files=files)
    assert resp.status_code == 201
    return db_session.get(Request, created["id"])


def test_start_review_creates_job_record_and_agent_rows(client, db_session, fake_llm):
    request = _request_with_evidence(client, db_session)

    run = start_review(db_session, request)

    assert run.status is ReviewRunStatus.PENDING
    assert run.model_name == "fake-model"
    assert run.policy_version
    assert {r.agent for r in run.agent_runs} == set(EXPECTED_AGENTS)
    assert all(r.state is AgentRunState.PENDING for r in run.agent_runs)
    # the request moves into REVIEWING immediately, before any agent runs
    assert db_session.get(Request, request.id).status is RequestStatus.REVIEWING


def test_second_concurrent_review_is_rejected(client, db_session, fake_llm):
    request = _request_with_evidence(client, db_session)
    start_review(db_session, request)

    with pytest.raises(ReviewAlreadyRunningError):
        start_review(db_session, request)


def test_successful_run_persists_agent_review(client, db_session, fake_llm):
    request = _request_with_evidence(client, db_session)
    fake_llm.default = valid_agent_payload()

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    db_session.refresh(run)
    assert run.status is ReviewRunStatus.COMPLETE
    assert all(r.state is AgentRunState.COMPLETE for r in run.agent_runs)
    assert review_is_complete(run) is True

    reviews = db_session.query(AgentReview).filter(AgentReview.review_run_id == run.id).all()
    assert {r.agent for r in reviews} == set(EXPECTED_AGENTS)
    product = next(r for r in reviews if r.agent is AgentType.PRODUCT)
    assert product.score == 72
    assert product.summary


def test_every_agent_prompt_carries_the_injection_rule_and_real_evidence_ids(
    client, db_session, fake_llm
):
    request = _request_with_evidence(client, db_session)
    fake_llm.default = valid_agent_payload()

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    assert len(fake_llm.calls) == len(EXPECTED_AGENTS)
    for call in fake_llm.calls:
        assert PROMPT_INJECTION_RULE in call["prompt"]
        # each agent is shown evidence ids it is permitted to cite
        assert "DOC-" in call["prompt"] and "-CHUNK-" in call["prompt"]


def test_each_agent_gets_its_own_taxonomy_and_retrieval_query(client, db_session, fake_llm):
    """The Phase 3 risk is seven prompts producing seven paraphrases. The
    taxonomy is the mitigation, so it must actually differ per agent -- and be
    enforced by the schema rather than only requested in prose."""
    request = _request_with_evidence(client, db_session)
    fake_llm.default = valid_agent_payload()

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    category_sets = []
    for call in fake_llm.calls:
        enum = call["schema"]["$defs"]["AgentFinding"]["properties"]["category"]["enum"]
        category_sets.append(frozenset(enum))
        # every category in the enum is also explained in that agent's prompt
        for code in enum:
            assert code in call["system"], f"{code} missing from its own system prompt"

    assert len(set(category_sets)) == len(EXPECTED_AGENTS), "agents share a taxonomy"

    # retrieval queries differ too, so agents are not reading identical evidence
    queries = {spec.retrieval_query for spec in AGENT_REGISTRY.values()}
    assert len(queries) == len(EXPECTED_AGENTS)


def test_shared_categories_are_only_the_deliberately_shared_ones(client, db_session, fake_llm):
    """INJECTION_ATTEMPT is intentionally on every agent -- any reviewer should
    be able to report a document trying to instruct it. Nothing else should
    overlap, or two reviewers are covering the same ground."""
    from itertools import combinations

    for a, b in combinations(AGENT_REGISTRY.values(), 2):
        shared = set(a.category_codes) & set(b.category_codes)
        assert shared <= {"INJECTION_ATTEMPT"}, (
            f"{a.agent.value} and {b.agent.value} overlap on {shared - {'INJECTION_ATTEMPT'}}"
        )


def test_agent_failure_marks_run_failed_without_placeholder_score(
    client, db_session, fake_llm
):
    request = _request_with_evidence(client, db_session)
    # fails both attempts
    fake_llm.default = LLMInvalidOutputError("not json")

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    db_session.refresh(run)
    assert all(r.state is AgentRunState.FAILED for r in run.agent_runs)
    agent_run = run.agent_runs[0]
    assert agent_run.error_class == "LLMInvalidOutputError"
    # crucially: no agent_reviews row was invented for the failed agent
    assert db_session.query(AgentReview).filter(AgentReview.review_run_id == run.id).count() == 0
    assert review_is_complete(run) is False
    assert run.error and "PRODUCT" in run.error


def test_ollama_unavailable_fails_the_agent_with_no_fallback(client, db_session, fake_llm):
    request = _request_with_evidence(client, db_session)
    fake_llm.default = LLMUnavailableError("connection refused")

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    db_session.refresh(run)
    assert all(r.state is AgentRunState.FAILED for r in run.agent_runs)
    assert run.agent_runs[0].error_class == "LLMUnavailableError"
    assert review_is_complete(run) is False


def test_retry_succeeds_on_second_attempt(client, db_session, fake_llm):
    request = _request_with_evidence(client, db_session)
    fake_llm.responses = [LLMInvalidOutputError("garbage")]
    fake_llm.default = valid_agent_payload()

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    db_session.refresh(run)
    # the first reviewer needed a retry; the rest succeeded first time
    assert all(r.state is AgentRunState.COMPLETE for r in run.agent_runs)
    assert max(r.attempts for r in run.agent_runs) == 2


def test_only_engineering_may_set_deadline_assessment(client, db_session, fake_llm):
    """Every reviewer volunteers a deadline verdict; only ENGINEERING keeps it,
    because the engine's B3/R5/R6 rules read that field."""
    request = _request_with_evidence(client, db_session)
    fake_llm.default = valid_agent_payload(deadline_assessment="INFEASIBLE")

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    reviews = {
        r.agent: r
        for r in db_session.query(AgentReview).filter(AgentReview.review_run_id == run.id).all()
    }
    assert reviews[AgentType.ENGINEERING].deadline_assessment is DeadlineAssessment.INFEASIBLE
    for agent, review in reviews.items():
        if agent is not AgentType.ENGINEERING:
            assert review.deadline_assessment is None, f"{agent.value} kept a deadline verdict"


def test_review_endpoint_returns_202_and_is_pollable(client, db_session, fake_llm):
    created = client.post("/api/requests", json=VALID_REQUEST_PAYLOAD).json()
    fake_llm.default = valid_agent_payload()

    resp = client.post(f"/api/requests/{created['id']}/review")
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] in ("PENDING", "RUNNING", "COMPLETE")
    assert len(body["agent_runs"]) == len(EXPECTED_AGENTS)

    poll = client.get(f"/api/reviews/{body['id']}")
    assert poll.status_code == 200
    assert poll.json()["id"] == body["id"]


def test_completed_run_persists_a_decision_and_audit_record(client, db_session, fake_llm):
    from app.core.enums import AuditEventType, DecisionStatus
    from app.db.models import AuditEvent, Decision

    request = _request_with_evidence(client, db_session)
    # score 72 with no blocker, no fail, one warning -> below the approve
    # average of 75, matches no REVISE rule -> the fallback
    fake_llm.default = valid_agent_payload()

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    decision = db_session.query(Decision).filter(Decision.review_run_id == run.id).one()
    assert decision.status is DecisionStatus.REVISE
    assert decision.review_complete is True
    # every reviewer PASSes at 72, so no rule fires and the average sits below
    # the approve floor -- exactly the case the mandatory fallback exists for
    assert decision.rule_ids == ["F1_FALLBACK_REVISE"]
    assert decision.policy_version and decision.model_name == "fake-model"

    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.event_type == AuditEventType.DECISION_CREATED)
        .one()
    )
    assert event.payload["deciding_rule_id"] == "F1_FALLBACK_REVISE"
    assert event.payload["document_ids"]  # evidence on the table is recorded


def test_failed_agent_run_produces_an_incomplete_decision_that_cannot_approve(
    client, db_session, fake_llm
):
    from app.core.enums import DecisionStatus
    from app.db.models import Decision

    request = _request_with_evidence(client, db_session)
    fake_llm.responses = [LLMUnavailableError("down"), LLMUnavailableError("down")]

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    decision = db_session.query(Decision).filter(Decision.review_run_id == run.id).one()
    assert decision.review_complete is False
    assert decision.status is not DecisionStatus.APPROVED
    assert "C1_REVIEW_INCOMPLETE" in decision.rule_ids


def test_decision_leaves_the_request_in_reviewing_until_a_human_acts(
    client, db_session, fake_llm
):
    request = _request_with_evidence(client, db_session)
    fake_llm.default = valid_agent_payload()

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    # the decision is a recommendation; only accept/override may move the request
    assert db_session.get(Request, request.id).status is RequestStatus.REVIEWING
