from sqlalchemy.orm import Session

from app.core.enums import AuditEventType
from app.db.models import AuditEvent


def record_event(
    db: Session,
    request_id,
    event_type: AuditEventType,
    actor: str = "system",
    payload: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        request_id=request_id,
        event_type=event_type,
        actor=actor,
        payload=payload,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
