"""Specialist reviewers.

Phase 2 registers PRODUCT only. Phase 3 adds the remaining six; the registry is
the single place that changes.
"""
from app.agents.base import AgentSpec
from app.agents.product import PRODUCT_SPEC
from app.core.enums import AgentType

AGENT_REGISTRY: dict[AgentType, AgentSpec] = {
    PRODUCT_SPEC.agent: PRODUCT_SPEC,
}

# The agents a review run is expected to include. The decision engine treats a
# run missing any of these as incomplete.
EXPECTED_AGENTS: frozenset[AgentType] = frozenset(AGENT_REGISTRY)

__all__ = ["AGENT_REGISTRY", "EXPECTED_AGENTS", "AgentSpec", "PRODUCT_SPEC"]
