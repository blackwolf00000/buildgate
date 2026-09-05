"""Local embedding providers.

Ollama is primary. If it's unreachable, we fall back to a local
sentence-transformers model rather than failing the whole ingestion pipeline
(this is the Phase 1 risk mitigation called out in the phase plan). The
fallback is never silent: whichever provider is actually active is reported
through GET /api/runtime, and a fallback logs a warning. This does not weaken
the "Ollama unreachable -> fail loudly" rule for LLM review calls in later
phases, which have no fallback at all.
"""
import logging
from typing import Protocol

from app.config import get_settings
from app.services.http_client import outbound_request

logger = logging.getLogger("buildgate.embeddings")


class EmbeddingProvider(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbeddingProvider:
    name = "ollama"

    def __init__(self, host: str, model: str):
        self.host = host.rstrip("/")
        self.model = model

    def ping(self) -> bool:
        try:
            resp = outbound_request("GET", f"{self.host}/api/tags", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            resp = outbound_request(
                "POST",
                f"{self.host}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=60.0,
            )
            resp.raise_for_status()
            vectors.append(resp.json()["embedding"])
        return vectors


class SentenceTransformersEmbeddingProvider:
    name = "sentence-transformers"

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(list(texts), normalize_embeddings=False)
        return [v.tolist() for v in vectors]


_active_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _active_provider
    if _active_provider is not None:
        return _active_provider

    settings = get_settings()
    if settings.embedding_provider == "ollama":
        candidate = OllamaEmbeddingProvider(settings.ollama_host, settings.embedding_model)
        if candidate.ping():
            logger.info("Embedding provider active: ollama (%s)", settings.embedding_model)
            _active_provider = candidate
            return _active_provider
        logger.warning(
            "Ollama unreachable at %s; falling back to local sentence-transformers model %s",
            settings.ollama_host,
            settings.sentence_transformers_model,
        )

    _active_provider = SentenceTransformersEmbeddingProvider(settings.sentence_transformers_model)
    return _active_provider


def set_embedding_provider(provider: EmbeddingProvider) -> None:
    """Test hook: inject a fake/deterministic provider."""
    global _active_provider
    _active_provider = provider


def reset_embedding_provider() -> None:
    global _active_provider
    _active_provider = None
