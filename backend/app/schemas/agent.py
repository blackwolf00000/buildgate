"""The common agent output schema.

This is the contract every reviewer returns, and the same model generates the
JSON Schema handed to Ollama's `format` parameter. Constraining generation and
validating afterwards are both required: `format` makes well-formed output the
overwhelmingly likely case, and Pydantic makes a malformed one an error rather
than a silent corruption.

`evidence_status` is deliberately *not* model-controlled -- it is set by
`app.services.evidence` after validating the IDs the model emitted against the
chunks actually retrieved for that call. See `EVIDENCE_MODEL_FIELDS`.
"""
from pydantic import BaseModel, Field, model_validator

from app.core.enums import (
    AgentStatus,
    AgentType,
    DeadlineAssessment,
    EvidenceStatus,
    FindingSeverity,
)


class AgentFinding(BaseModel):
    # `category` is constrained to the agent's own taxonomy by a JSON Schema
    # enum at the model call, so a reviewer cannot raise a finding outside its
    # remit. The title is deliberately free text: the category says which kind
    # of problem this is, the title says what is actually wrong with *this*
    # request.
    category: str
    severity: FindingSeverity
    title: str
    description: str
    evidence_ids: list[str] = Field(default_factory=list)


class AgentReviewOutput(BaseModel):
    """Exactly what the model is asked to produce."""

    agent: AgentType
    score: int = Field(ge=0, le=100)
    status: AgentStatus
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    findings: list[AgentFinding] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    critical_information_missing: bool = False
    deadline_assessment: DeadlineAssessment | None = None

    @model_validator(mode="after")
    def adverse_verdicts_need_a_finding(self) -> "AgentReviewOutput":
        """A FAIL or BLOCK with no findings is not a usable review.

        Observed in practice: reviewers returned status FAIL with a summary
        describing problems and an empty findings list, which gives a reader
        nothing to act on and gives the decision engine no severity to weigh.
        Raising here means `run_agent` retries with a different seed rather
        than persisting an unusable verdict.
        """
        if self.status in (AgentStatus.FAIL, AgentStatus.BLOCK) and not self.findings:
            raise ValueError(
                f"status {self.status.value} requires at least one finding to justify it"
            )
        return self


class ValidatedFinding(AgentFinding):
    """A finding after evidence validation.

    `evidence_ids` holds only IDs that resolve to a chunk actually retrieved
    for this agent call. `stripped_evidence_ids` records what was removed, so a
    fabricated reference is auditable rather than merely gone.
    """

    evidence_status: EvidenceStatus = EvidenceStatus.OK
    stripped_evidence_ids: list[str] = Field(default_factory=list)


def ollama_format_schema(categories: tuple[str, ...] = ()) -> dict:
    """JSON Schema for Ollama's `format` parameter.

    Derived from the Pydantic model so the two can never drift. The evidence
    validation fields are excluded -- the model is not asked to produce them.

    When `categories` is given, the finding `category` field is narrowed to an
    enum of exactly that agent's taxonomy. Constraining it at generation time is
    stronger than asking in the prompt and dropping strays afterwards: the model
    is structurally unable to raise a finding belonging to another reviewer.
    """
    schema = AgentReviewOutput.model_json_schema()
    schema.pop("title", None)

    if categories:
        finding = schema.get("$defs", {}).get("AgentFinding")
        if finding is not None:
            finding["properties"]["category"] = {
                "type": "string",
                "enum": list(categories),
            }
    return schema
