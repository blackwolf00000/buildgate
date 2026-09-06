"""Evidence grounding is a control, not a prompt instruction.

The model will emit plausible-looking evidence IDs that refer to nothing. These
tests assert that such IDs are stripped in code, and that a finding left with
nothing to stand on is demoted rather than displayed as grounded.
"""
import uuid

from app.core.enums import EvidenceStatus, FindingSeverity
from app.schemas.agent import AgentFinding
from app.services.evidence import validate_findings


def _real_id(index: int = 0) -> str:
    return f"DOC-{uuid.uuid4()}-CHUNK-{index}"


def test_fabricated_evidence_id_is_stripped():
    real = _real_id()
    fake = f"DOC-{uuid.uuid4()}-CHUNK-7"

    findings = [
        AgentFinding(
            severity=FindingSeverity.HIGH,
            title="Export bypasses classification review",
            description="...",
            evidence_ids=[real, fake],
        )
    ]

    result = validate_findings(findings, {real})

    assert result[0].evidence_ids == [real]
    assert result[0].stripped_evidence_ids == [fake]
    # still grounded -- one real citation survived
    assert result[0].evidence_status is EvidenceStatus.OK


def test_finding_with_only_fabricated_evidence_is_demoted_to_missing():
    real = _real_id()
    fake_a = f"DOC-{uuid.uuid4()}-CHUNK-0"
    fake_b = f"DOC-{uuid.uuid4()}-CHUNK-1"

    findings = [
        AgentFinding(
            severity=FindingSeverity.CRITICAL,
            title="Invented policy breach",
            description="...",
            evidence_ids=[fake_a, fake_b],
        )
    ]

    result = validate_findings(findings, {real})

    assert result[0].evidence_ids == []
    assert result[0].stripped_evidence_ids == [fake_a, fake_b]
    assert result[0].evidence_status is EvidenceStatus.MISSING


def test_significant_finding_with_no_evidence_at_all_is_missing():
    findings = [
        AgentFinding(
            severity=FindingSeverity.HIGH,
            title="Asserted with no citation",
            description="...",
            evidence_ids=[],
        )
    ]

    result = validate_findings(findings, {_real_id()})

    assert result[0].evidence_status is EvidenceStatus.MISSING


def test_informational_finding_without_evidence_is_not_flagged():
    # INFO/LOW observations are allowed to stand without citations; flagging
    # them as MISSING would drown the real signal.
    findings = [
        AgentFinding(
            severity=FindingSeverity.INFO,
            title="Request is clearly written",
            description="...",
            evidence_ids=[],
        )
    ]

    result = validate_findings(findings, {_real_id()})

    assert result[0].evidence_status is EvidenceStatus.OK


def test_agent_may_only_cite_chunks_it_was_shown():
    # A real, resolvable ID that belongs to a different agent's retrieval set
    # is still stripped -- "real" is not the test, "retrieved for this call" is.
    shown = _real_id(0)
    not_shown = _real_id(1)

    findings = [
        AgentFinding(
            severity=FindingSeverity.MEDIUM,
            title="Cites a chunk from another agent's context",
            description="...",
            evidence_ids=[not_shown],
        )
    ]

    result = validate_findings(findings, {shown})

    assert result[0].evidence_ids == []
    assert result[0].stripped_evidence_ids == [not_shown]
    assert result[0].evidence_status is EvidenceStatus.MISSING


def test_duplicate_evidence_ids_are_collapsed():
    real = _real_id()
    findings = [
        AgentFinding(
            severity=FindingSeverity.MEDIUM,
            title="Cites the same chunk twice",
            description="...",
            evidence_ids=[real, real],
        )
    ]

    result = validate_findings(findings, {real})

    assert result[0].evidence_ids == [real]


def test_blank_and_malformed_ids_are_stripped():
    real = _real_id()
    findings = [
        AgentFinding(
            severity=FindingSeverity.MEDIUM,
            title="Emits junk",
            description="...",
            evidence_ids=["", "   ", "not-an-evidence-id", real],
        )
    ]

    result = validate_findings(findings, {real})

    assert result[0].evidence_ids == [real]
    assert "not-an-evidence-id" in result[0].stripped_evidence_ids
