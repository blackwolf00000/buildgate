import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditEventOut(BaseModel):
    id: uuid.UUID
    event_type: str
    actor: str
    payload: dict | None
    created_at: datetime

    class Config:
        from_attributes = True
