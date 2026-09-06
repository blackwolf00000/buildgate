"""Feature 5: a named human decides, and the record is permanent.

The load-bearing test here is that an override cannot be submitted with any
field missing -- enforced server-side, not merely disabled in a form. Every
required field is exercised individually, and blank strings and empty lists are
treated as missing, because a risk owner of "" is not a risk owner and an empty
accepted-risks list is not consent.
"""
import pytest

from app.core.enums import AuditEventType, DecisionStatus, RequestStatus
from app.db.models import AuditEvent, Decision, Request
from app.services.decisions import (
    DecisionAlreadyResolvedError,
    OverrideValidationError,
    accept_decision,
    override_decision,
    request_revision,
)
from app.services.review import execute_review, start_review
from tests.conftest import VALID_REQUEST_PAYLOAD, valid_agent_payload

VALID_OVERRIDE = {
    "actor": "Dana Whitfield",
    "override_reason": "Regulatory deadline leaves no room to re-scope this quarter.",
    "override_risk_owner": "Priya Raman, VP Engineering",
    "override_approver_name": "Marcus Webb, CTO",
    "override_accepted_risks": ["Export may include internal-only fields"],
}


def _decided_request(client, db_session, fake_llm, **agent_overrides):
    """Drive a request through a full review so a decision row exists."""
    created = client.post("/api/requests", json=VALID_REQUEST_PAYLOAD).json()
    fake_llm.responses = [valid_agent_payload(**agent_overrides)]
    request = db_session.get(Request, created["id"])

    run = start_review(db_session, request)
    execute_review(db_session, run.id)

    decision = db_session.query(Decision).filter(Decision.review_run_id == run.id).one()
    return request, decision


# --- the exit criterion ----------------------------------------------------

@pytest.mark.parametrize(
    "missing_field",
    [
        "override_reason",
        "override_risk_owner",
        "override_approver_name",
        "override_accepted_risks",
    ],
)
def test_override_rejected_when_a_field_is_absent(
    client, db_session, fake_llm, missing_field
):
    _, decision = _decided_request(client, db_session, fake_llm)

    payload = dict(VALID_OVERRIDE)
    payload.pop(missing_field)

    resp = client.post(f"/api/decisions/{decision.id}/override", json=payload)
    assert resp.status_code == 422

    db_session.refresh(decision)
    assert decision.overridden_at is None


@pytest.mark.parametrize(
    "field,blank_value",
    [
        ("override_reason", "   "),
        ("override_risk_owner", ""),
        ("override_approver_name", "  "),
        ("override_accepted_risks", []),
        ("override_accepted_risks", ["", "   "]),
        ("actor", " "),
    ],
)
def test_override_rejected_when_a_field_is_blank(
    client, db_session, fake_llm, field, blank_value
):
    """A blank field is a missing field. Whitespace is not accountability."""
    _, decision = _decided_request(client, db_session, fake_llm)

    payload = dict(VALID_OVERRIDE)
    payload[field] = blank_value

    resp = client.post(f"/api/decisions/{decision.id}/override", json=payload)
    assert resp.status_code == 422

    db_session.refresh(decision)
    assert decision.overridden_at is None


def test_service_layer_rejects_override_independently_of_the_schema(
    client, db_session, fake_llm
):
    """The requirement is server-side enforcement, so the service must not
    depend on a caller having validated first."""
    _, decision = _decided_request(client, db_session, fake_llm)

    with pytest.raises(OverrideValidationError) as exc:
        override_decision(
            db_session,
            decision,
            actor="Dana",
            override_reason="   ",
            override_risk_owner="Priya",
            override_approver_name="Marcus",
            override_accepted_risks=[],
        )

    message = str(exc.value)
    assert "override_reason" in message and "override_accepted_risks" in message
    db_session.refresh(decision)
    assert decision.overridden_at is None


# --- the happy paths -------------------------------------------------------

def test_valid_override_is_recorded_with_full_accountability(
    client, db_session, fake_llm
):
    request, decision = _decided_request(client, db_session, fake_llm)

    resp = client.post(f"/api/decisions/{decision.id}/override", json=VALID_OVERRIDE)
    assert resp.status_code == 200

    db_session.refresh(decision)
    assert decision.overridden_at is not None
    assert decision.override_risk_owner == "Priya Raman, VP Engineering"
    assert decision.override_approver_name == "Marcus Webb, CTO"
    assert decision.override_accepted_risks == ["Export may include internal-only fields"]
    assert db_session.get(Request, request.id).status is RequestStatus.OVERRIDDEN

    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.event_type == AuditEventType.DECISION_OVERRIDDEN)
        .one()
    )
    assert event.actor == "Dana Whitfield"
    # enough to explain the outcome without reading source
    assert event.payload["overridden_status"] == decision.status.value
    assert event.payload["policy_version"] and event.payload["model_name"]
    assert event.payload["rule_ids"] == decision.rule_ids


def test_accept_applies_the_recommendation_to_the_request(client, db_session, fake_llm):
    request, decision = _decided_request(client, db_session, fake_llm)

    resp = client.post(
        f"/api/decisions/{decision.id}/accept", json={"actor": "Marcus Webb"}
    )
    assert resp.status_code == 200

    db_session.refresh(decision)
    assert decision.accepted_by == "Marcus Webb"
    assert decision.accepted_at is not None
    # the fake agent scores 72 -> the engine's fallback REVISE
    assert decision.status is DecisionStatus.REVISE
    assert db_session.get(Request, request.id).status is RequestStatus.REVISE

    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.event_type == AuditEventType.DECISION_ACCEPTED)
        .one()
    )
    assert event.actor == "Marcus Webb"


def test_accepting_an_approval_moves_the_request_to_approved(client, db_session, fake_llm):
    request, decision = _decided_request(
        client, db_session, fake_llm, score=90, status="PASS"
    )
    assert decision.status is DecisionStatus.APPROVED

    client.post(f"/api/decisions/{decision.id}/accept", json={"actor": "Marcus Webb"})
    assert db_session.get(Request, request.id).status is RequestStatus.APPROVED


def test_send_for_revision_overrides_an_approval(client, db_session, fake_llm):
    """A human may send a request back even when the board approved it."""
    request, decision = _decided_request(
        client, db_session, fake_llm, score=90, status="PASS"
    )
    assert decision.status is DecisionStatus.APPROVED

    resp = client.post(
        f"/api/decisions/{decision.id}/revision",
        json={"actor": "Marcus Webb", "note": "Wait for the security review."},
    )
    assert resp.status_code == 200
    assert db_session.get(Request, request.id).status is RequestStatus.REVISE

    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.event_type == AuditEventType.REVISION_REQUESTED)
        .one()
    )
    assert event.payload["recommended_status"] == "APPROVED"
    assert event.payload["note"] == "Wait for the security review."


def test_actor_is_mandatory_on_every_action(client, db_session, fake_llm):
    _, decision = _decided_request(client, db_session, fake_llm)

    for path in ("accept", "revision"):
        assert client.post(f"/api/decisions/{decision.id}/{path}", json={}).status_code == 422
        assert (
            client.post(f"/api/decisions/{decision.id}/{path}", json={"actor": "  "}).status_code
            == 422
        )


# --- append-only integrity -------------------------------------------------

def test_a_decision_cannot_be_resolved_twice(client, db_session, fake_llm):
    _, decision = _decided_request(client, db_session, fake_llm)

    client.post(f"/api/decisions/{decision.id}/accept", json={"actor": "Marcus"})
    second = client.post(f"/api/decisions/{decision.id}/accept", json={"actor": "Marcus"})
    assert second.status_code == 409

    overridden = client.post(f"/api/decisions/{decision.id}/override", json=VALID_OVERRIDE)
    assert overridden.status_code == 409


def test_an_overridden_decision_cannot_then_be_accepted(client, db_session, fake_llm):
    _, decision = _decided_request(client, db_session, fake_llm)

    client.post(f"/api/decisions/{decision.id}/override", json=VALID_OVERRIDE)

    with pytest.raises(DecisionAlreadyResolvedError):
        accept_decision(db_session, decision, "Marcus")
    with pytest.raises(DecisionAlreadyResolvedError):
        request_revision(db_session, decision, "Marcus")


def test_audit_trail_reconstructs_the_full_history(client, db_session, fake_llm):
    request, decision = _decided_request(client, db_session, fake_llm)
    client.post(f"/api/decisions/{decision.id}/override", json=VALID_OVERRIDE)

    events = client.get(f"/api/requests/{request.id}/audit").json()
    types = [e["event_type"] for e in events]

    for expected in (
        "REQUEST_CREATED",
        "REVIEW_STARTED",
        "AGENT_REVIEW_COMPLETED",
        "DECISION_CREATED",
        "DECISION_OVERRIDDEN",
    ):
        assert expected in types, f"{expected} missing from the audit trail"


def test_unknown_decision_returns_404(client, db_session, fake_llm):
    import uuid as _uuid

    resp = client.post(
        f"/api/decisions/{_uuid.uuid4()}/accept", json={"actor": "Marcus"}
    )
    assert resp.status_code == 404
