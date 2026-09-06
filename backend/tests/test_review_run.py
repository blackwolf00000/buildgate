"""Review run orchestration: job records, agent failure handling, prompting."""
import io

import pytest

from app.agents import EXPECTED_AGENTS
from app.agents.base import PROMPT_INJECTION_RULE
from app.core.enums import AgentRunState, RequestStatus, ReviewRunStatus
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
    fake_llm.responses = [valid_agent_payload()]

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    db_session.refresh(run)
    assert run.status is ReviewRunStatus.COMPLETE
    assert all(r.state is AgentRunState.COMPLETE for r in run.agent_runs)
    assert review_is_complete(run) is True

    review = db_session.query(AgentReview).filter(AgentReview.review_run_id == run.id).one()
    assert review.agent.value == "PRODUCT"
    assert review.score == 72
    assert review.summary


def test_prompt_carries_injection_rule_and_real_evidence_ids(client, db_session, fake_llm):
    request = _request_with_evidence(client, db_session)
    fake_llm.responses = [valid_agent_payload()]

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    call = fake_llm.calls[0]
    assert PROMPT_INJECTION_RULE in call["prompt"]
    # the agent is shown evidence ids it is permitted to cite
    assert "DOC-" in call["prompt"] and "-CHUNK-" in call["prompt"]
    # and its taxonomy is stated, so it cannot roam into another remit
    assert "PROBLEM_EVIDENCE" in call["system"]
    # determinism is enforced at the provider, and the schema is passed through
    assert call["schema"]["properties"]["status"]


def test_agent_failure_marks_run_failed_without_placeholder_score(
    client, db_session, fake_llm
):
    request = _request_with_evidence(client, db_session)
    # fails both attempts
    fake_llm.responses = [
        LLMInvalidOutputError("not json"),
        LLMInvalidOutputError("not json"),
    ]

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    db_session.refresh(run)
    agent_run = run.agent_runs[0]
    assert agent_run.state is AgentRunState.FAILED
    assert agent_run.error_class == "LLMInvalidOutputError"
    # crucially: no agent_reviews row was invented for the failed agent
    assert db_session.query(AgentReview).filter(AgentReview.review_run_id == run.id).count() == 0
    assert review_is_complete(run) is False
    assert run.error and "PRODUCT" in run.error


def test_ollama_unavailable_fails_the_agent_with_no_fallback(client, db_session, fake_llm):
    request = _request_with_evidence(client, db_session)
    fake_llm.responses = [LLMUnavailableError("connection refused")]

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    db_session.refresh(run)
    assert run.agent_runs[0].state is AgentRunState.FAILED
    assert run.agent_runs[0].error_class == "LLMUnavailableError"
    assert review_is_complete(run) is False


def test_retry_succeeds_on_second_attempt(client, db_session, fake_llm):
    request = _request_with_evidence(client, db_session)
    fake_llm.responses = [LLMInvalidOutputError("garbage"), valid_agent_payload()]

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    db_session.refresh(run)
    assert run.agent_runs[0].state is AgentRunState.COMPLETE
    assert run.agent_runs[0].attempts == 2


def test_non_engineering_agent_cannot_set_deadline_assessment(
    client, db_session, fake_llm
):
    request = _request_with_evidence(client, db_session)
    # PRODUCT volunteers a deadline verdict it has no remit for
    fake_llm.responses = [valid_agent_payload(deadline_assessment="INFEASIBLE")]

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    review = db_session.query(AgentReview).filter(AgentReview.review_run_id == run.id).one()
    assert review.deadline_assessment is None


def test_review_endpoint_returns_202_and_is_pollable(client, db_session, fake_llm):
    created = client.post("/api/requests", json=VALID_REQUEST_PAYLOAD).json()
    fake_llm.responses = [valid_agent_payload()]

    resp = client.post(f"/api/requests/{created['id']}/review")
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] in ("PENDING", "RUNNING", "COMPLETE")
    assert len(body["agent_runs"]) == len(EXPECTED_AGENTS)

    poll = client.get(f"/api/reviews/{body['id']}")
    assert poll.status_code == 200
    assert poll.json()["id"] == body["id"]
