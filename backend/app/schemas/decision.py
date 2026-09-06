"""Human accountability actions on a decision.

The override payload is validated here *and* the same rules are enforced in the
service layer, because the requirement is explicit that an override must be
impossible to submit with a missing field server-side -- not merely disabled in
the form. Blank strings and empty lists are rejected as hard as absent keys: a
risk owner of "" is a missing risk owner, and accepted_risks must be explicitly
ticked, so an empty list is not consent.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _require_text(value: str, field: str) -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"{field} is required")
    return str(value).strip()


class ActorIn(BaseModel):
    """AI recommends; a named human decides. The name is not optional."""

    actor: str = Field(min_length=1)

    @field_validator("actor")
    @classmethod
    def actor_not_blank(cls, v: str) -> str:
        return _require_text(v, "actor")


class RevisionIn(ActorIn):
    note: str | None = None


class OverrideIn(ActorIn):
    override_reason: str = Field(min_length=1)
    override_risk_owner: str = Field(min_length=1)
    override_approver_name: str = Field(min_length=1)
    override_accepted_risks: list[str] = Field(min_length=1)

    @field_validator("override_reason")
    @classmethod
    def reason_not_blank(cls, v: str) -> str:
        return _require_text(v, "override_reason")

    @field_validator("override_risk_owner")
    @classmethod
    def risk_owner_not_blank(cls, v: str) -> str:
        return _require_text(v, "override_risk_owner")

    @field_validator("override_approver_name")
    @classmethod
    def approver_not_blank(cls, v: str) -> str:
        return _require_text(v, "override_approver_name")

    @field_validator("override_accepted_risks")
    @classmethod
    def risks_explicitly_ticked(cls, v: list[str]) -> list[str]:
        cleaned = [str(r).strip() for r in v if r is not None and str(r).strip()]
        if not cleaned:
            raise ValueError(
                "override_accepted_risks must contain at least one explicitly accepted risk"
            )
        return cleaned


class DecisionOut(BaseModel):
    id: uuid.UUID
    review_run_id: uuid.UUID
    request_id: uuid.UUID
    status: str
    policy_version: str
    model_name: str
    review_complete: bool
    rule_ids: list[str] = []

    accepted_at: datetime | None = None
    accepted_by: str | None = None
    overridden_at: datetime | None = None
    override_reason: str | None = None
    override_risk_owner: str | None = None
    override_accepted_risks: list[str] | None = None
    override_approver_name: str | None = None

    created_at: datetime

    class Config:
        from_attributes = True
