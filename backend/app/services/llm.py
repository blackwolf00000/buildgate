"""Local LLM access for agent review calls.

Deliberately has **no fallback path**. The embedding pipeline may fall back to
a bundled sentence-transformers model when Ollama is down (see
`app.services.embeddings`), because a missing embedding degrades retrieval
quality. A missing *reviewer* is different: substituting anything for a
governance judgement would be worse than failing, so when Ollama is unreachable
this raises and the agent is marked failed. That is the
"Ollama unreachable -> fail loudly, never degrade silently" rule from the
customer-isolation constraint.
"""
import json
import logging
from typing import Protocol

import httpx

from app.config import get_settings
from app.services.http_client import outbound_request

logger = logging.getLogger("buildgate.llm")


class LLMUnavailableError(Exception):
    """Ollama could not be reached, or returned a transport-level failure."""


class LLMInvalidOutputError(Exception):
    """Ollama responded, but the payload was not usable JSON."""


class LLMProvider(Protocol):
    name: str
    model: str

    def generate_json(self, system: str, prompt: str, schema: dict, attempt: int = 1) -> dict: ...


class OllamaProvider:
    """Schema-constrained generation against a local Ollama server."""

    name = "ollama"

    def __init__(
        self,
        host: str,
        model: str,
        temperature: float,
        seed: int,
        timeout: float,
        num_ctx: int = 8192,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self.timeout = timeout
        self.num_ctx = num_ctx

    def generate_json(self, system: str, prompt: str, schema: dict, attempt: int = 1) -> dict:
        """One constrained call. Raises rather than returning anything partial.

        `attempt` offsets the seed. temperature=0 with a fixed seed makes a
        retry byte-identical to the call that just failed, so a plain retry
        would be a guaranteed no-op. Offsetting by the attempt number keeps the
        run reproducible -- attempt N of a given input is always the same --
        while still drawing a different sample.
        """
        payload = {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            # Constrain generation to the schema at the model call, rather than
            # asking for JSON in the prompt and repairing the result.
            "format": schema,
            "options": {
                # Determinism: identical inputs must produce identical output.
                "temperature": self.temperature,
                "seed": self.seed + (attempt - 1),
                # Explicit, not the model default -- see Settings.llm_num_ctx.
                "num_ctx": self.num_ctx,
            },
        }

        try:
            response = outbound_request(
                "POST", f"{self.host}/api/generate", json=payload, timeout=self.timeout
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Ollama call failed: {type(exc).__name__}") from exc

        body = response.json()
        raw = body.get("response")
        if not raw:
            raise LLMInvalidOutputError("Ollama returned an empty response body")

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMInvalidOutputError("Ollama response was not valid JSON") from exc


_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        _provider = OllamaProvider(
            host=settings.ollama_host,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            seed=settings.llm_seed,
            timeout=settings.llm_timeout_seconds,
            num_ctx=settings.llm_num_ctx,
        )
    return _provider


def set_llm_provider(provider: LLMProvider) -> None:
    """Test hook: inject a deterministic fake so the suite never needs Ollama."""
    global _provider
    _provider = provider


def reset_llm_provider() -> None:
    global _provider
    _provider = None
