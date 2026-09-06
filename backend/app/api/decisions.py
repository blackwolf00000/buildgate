import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.requests import _get_request_or_404
from app.db.models import Decision
from app.db.session import get_db
from app.schemas.decision import ActorIn, DecisionOut, OverrideIn, RevisionIn
from app.services.decisions import (
    DecisionAlreadyResolvedError,
    OverrideValidationError,
    accept_decision,
    override_decision,
    request_revision,
)

router = APIRouter(prefix="/api")


def _get_decision_or_404(db: Session, decision_id: uuid.UUID) -> Decision:
    decision = db.get(Decision, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return decision


@router.get("/requests/{request_id}/decisions", response_model=list[DecisionOut])
def list_decisions(request_id: uuid.UUID, db: Session = Depends(get_db)):
    """Newest first. Re-running a review adds a row; it never replaces one."""
    _get_request_or_404(db, request_id)
    return (
        db.query(Decision)
        .filter(Decision.request_id == request_id)
        .order_by(Decision.created_at.desc())
        .all()
    )


@router.get("/decisions/{decision_id}", response_model=DecisionOut)
def get_decision(decision_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_decision_or_404(db, decision_id)


@router.post("/decisions/{decision_id}/accept", response_model=DecisionOut)
def accept(decision_id: uuid.UUID, payload: ActorIn, db: Session = Depends(get_db)):
    decision = _get_decision_or_404(db, decision_id)
    try:
        return accept_decision(db, decision, payload.actor)
    except DecisionAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/decisions/{decision_id}/revision", response_model=DecisionOut)
def send_for_revision(decision_id: uuid.UUID, payload: RevisionIn, db: Session = Depends(get_db)):
    decision = _get_decision_or_404(db, decision_id)
    try:
        return request_revision(db, decision, payload.actor, payload.note)
    except DecisionAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/decisions/{decision_id}/override", response_model=DecisionOut)
def override(decision_id: uuid.UUID, payload: OverrideIn, db: Session = Depends(get_db)):
    decision = _get_decision_or_404(db, decision_id)
    try:
        return override_decision(
            db,
            decision,
            actor=payload.actor,
            override_reason=payload.override_reason,
            override_risk_owner=payload.override_risk_owner,
            override_approver_name=payload.override_approver_name,
            override_accepted_risks=payload.override_accepted_risks,
        )
    except OverrideValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DecisionAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
