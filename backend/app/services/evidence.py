"""Evidence grounding.

The model will emit plausible-looking `evidence_id` values that refer to
nothing. A prompt instruction is not a control, so every ID a finding carries is
checked here against the set of chunks actually retrieved for that specific
agent call. IDs that do not resolve are stripped; a finding left with no valid
evidence is demoted to `evidence_status: MISSING` rather than being shown as
though it were grounded.

Stripped IDs are retained on the finding (`stripped_evidence_ids`) so a
fabrication is auditable after the fact instead of silently disappearing.
"""
import logging
import re

from app.core.enums import EvidenceStatus, FindingSeverity
from app.schemas.agent import AgentFinding, ValidatedFinding

logger = logging.getLogger("buildgate.evidence")

# DOC-{uuid}-CHUNK-{int}, produced by app.services.retrieval.evidence_id_for
EVIDENCE_ID_PATTERN = re.compile(
    r"^DOC-(?P<document_id>[0-9a-fA-F-]{36})-CHUNK-(?P<chunk_index>\d+)$"
)

# Severities significant enough that an ungrounded claim matters. INFO/LOW
# findings are commentary; HIGH/CRITICAL ones drive the decision engine.
SIGNIFICANT_SEVERITIES = frozenset(
    {FindingSeverity.MEDIUM, FindingSeverity.HIGH, FindingSeverity.CRITICAL}
)


def validate_findings(
    findings: list[AgentFinding], allowed_evidence_ids: set[str]
) -> list[ValidatedFinding]:
    """Strip unresolvable evidence IDs and demote ungrounded findings.

    `allowed_evidence_ids` must be the evidence IDs of the chunks retrieved for
    this agent call -- not every chunk in the request. An agent may only cite
    what it was actually shown.
    """
    validated: list[ValidatedFinding] = []

    for finding in findings:
        kept: list[str] = []
        stripped: list[str] = []

        for raw_id in finding.evidence_ids:
            evidence_id = (raw_id or "").strip()
            if evidence_id and evidence_id in allowed_evidence_ids:
                if evidence_id not in kept:
                    kept.append(evidence_id)
            else:
                stripped.append(evidence_id)

        if stripped:
            logger.warning(
                "Stripped %d unresolvable evidence id(s) from finding %r",
                len(stripped),
                finding.title,
            )

        # A significant finding with nothing left to stand on is MISSING.
        # INFO/LOW findings are allowed to carry no evidence at all, so an
        # observation that never cited anything is not marked as though it had
        # tried and failed.
        if kept:
            status = EvidenceStatus.OK
        elif finding.severity in SIGNIFICANT_SEVERITIES:
            status = EvidenceStatus.MISSING
        elif stripped:
            status = EvidenceStatus.MISSING
        else:
            status = EvidenceStatus.OK

        validated.append(
            ValidatedFinding(
                severity=finding.severity,
                title=finding.title,
                description=finding.description,
                evidence_ids=kept,
                stripped_evidence_ids=stripped,
                evidence_status=status,
            )
        )

    return validated
