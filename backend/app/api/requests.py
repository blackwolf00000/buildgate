import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.enums import AuditEventType
from app.db.models import Request
from app.db.session import get_db
from app.schemas.common import AuditEventOut
from app.schemas.request import RequestCreate, RequestOut, RequestUpdate
from app.services.audit import record_event

router = APIRouter(prefix="/api/requests")


def _get_request_or_404(db: Session, request_id: str | uuid.UUID) -> Request:
    # Routes vary: the Phase 1 handlers take the path param as a str, the
    # review/evidence handlers let FastAPI parse it to a UUID. Accept both.
    try:
        rid = request_id if isinstance(request_id, uuid.UUID) else uuid.UUID(str(request_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=404, detail="Request not found")
    obj = db.get(Request, rid)
    if obj is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return obj


@router.post("", response_model=RequestOut, status_code=201)
def create_request(payload: RequestCreate, db: Session = Depends(get_db)):
    obj = Request(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)

    record_event(
        db,
        obj.id,
        AuditEventType.REQUEST_CREATED,
        actor=obj.requester or "system",
        payload={"title": obj.title},
    )
    return obj


@router.get("", response_model=list[RequestOut])
def list_requests(db: Session = Depends(get_db)):
    return db.query(Request).order_by(Request.created_at.desc()).all()


@router.get("/{request_id}", response_model=RequestOut)
def get_request(request_id: str, db: Session = Depends(get_db)):
    return _get_request_or_404(db, request_id)


@router.patch("/{request_id}", response_model=RequestOut)
def update_request(request_id: str, payload: RequestUpdate, db: Session = Depends(get_db)):
    obj = _get_request_or_404(db, request_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{request_id}/audit", response_model=list[AuditEventOut])
def get_audit_trail(request_id: str, db: Session = Depends(get_db)):
    obj = _get_request_or_404(db, request_id)
    return sorted(obj.audit_events, key=lambda e: e.created_at)
