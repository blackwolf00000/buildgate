"""Specialist reviewers.

Adding a reviewer is a new `AgentSpec` module registered here; `EXPECTED_AGENTS`
derives from the registry, and the decision engine's completeness stage picks it
up with no further change.

Agents were added in pairs with a differentiation check after each pair, per the
Phase 3 plan -- the named risk is seven prompts producing seven paraphrases of
the same observation.
"""
from app.agents.architecture import ARCHITECTURE_SPEC
from app.agents.ba import BA_SPEC
from app.agents.base import AgentSpec
from app.agents.engineering import ENGINEERING_SPEC
from app.agents.product import PRODUCT_SPEC
from app.agents.qa import QA_SPEC
from app.agents.security import SECURITY_SPEC
from app.agents.user_evidence import USER_EVIDENCE_SPEC
from app.core.enums import AgentType

AGENT_REGISTRY: dict[AgentType, AgentSpec] = {
    spec.agent: spec
    for spec in (
        PRODUCT_SPEC,
        SECURITY_SPEC,
        ENGINEERING_SPEC,
        ARCHITECTURE_SPEC,
        QA_SPEC,
        BA_SPEC,
        USER_EVIDENCE_SPEC,
    )
}

# The agents a review run is expected to include. The decision engine treats a
# run missing any of these as incomplete.
EXPECTED_AGENTS: frozenset[AgentType] = frozenset(AGENT_REGISTRY)

__all__ = [
    "AGENT_REGISTRY",
    "EXPECTED_AGENTS",
    "AgentSpec",
    "ARCHITECTURE_SPEC",
    "BA_SPEC",
    "ENGINEERING_SPEC",
    "PRODUCT_SPEC",
    "QA_SPEC",
    "SECURITY_SPEC",
    "USER_EVIDENCE_SPEC",
]
