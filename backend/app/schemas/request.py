import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import RequestStatus


class RequestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1)
    business_reason: str = Field(min_length=1)
    requested_deadline: date
    deadline_is_fixed: bool = Field(
        description="This deadline is contractually or externally fixed."
    )

    requester: str | None = None
    department: str | None = None
    expected_outcome: str | None = None
    target_users: str | None = None
    priority: str | None = None
    notes: str | None = None


class RequestUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, min_length=1)
    business_reason: str | None = Field(default=None, min_length=1)
    requested_deadline: date | None = None
    deadline_is_fixed: bool | None = None

    requester: str | None = None
    department: str | None = None
    expected_outcome: str | None = None
    target_users: str | None = None
    priority: str | None = None
    notes: str | None = None


class RequestOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    business_reason: str
    requested_deadline: date
    deadline_is_fixed: bool

    requester: str | None
    department: str | None
    expected_outcome: str | None
    target_users: str | None
    priority: str | None
    notes: str | None

    status: RequestStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
