from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://buildgate:buildgate@db:5432/buildgate"

    ollama_host: str = "http://host.docker.internal:11434"
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768
    sentence_transformers_model: str = "all-mpnet-base-v2"

    max_upload_mb: int = 10
    allowed_upload_extensions: str = ".md,.txt"
    storage_dir: str = "/data/uploads"

    outbound_allowed_hosts: str = "localhost,127.0.0.1,host.docker.internal,ollama"

    retrieval_small_corpus_threshold: int = 60
    retrieval_top_k: int = 8

    chunk_size: int = 1000
    chunk_overlap: int = 150

    # --- LLM review calls (Phase 2). No fallback provider by design. ---
    # qwen2.5:3b is the default because it is what has actually been verified
    # end to end here: it grounds its findings and fits alongside the stack in
    # ~8GB. llama3 (8B) needs ~5GB of weights and will not load on such a host.
    llm_model: str = "qwen2.5:3b"
    llm_temperature: float = 0.0
    llm_seed: int = 42
    llm_timeout_seconds: float = 300.0
    # Ollama sizes the KV cache and compute buffers from the context window,
    # and a model's default can be enormous (qwen2.5 ships 32k). On a memory-
    # constrained host that allocation fails before generation starts, with an
    # opaque HTTP 500. Pin it to something the prompt actually needs.
    llm_num_ctx: int = 8192
    llm_max_attempts: int = 2  # one retry, then the agent is marked failed

    # --- Decision engine (see buildgate-decision-engine-spec.md) ---
    # Thresholds live here, never inline in the engine, so policy can be tuned
    # without touching rule code. Changing any of these means bumping
    # policy_version.
    policy_version: str = "2026.09.1"
    confidence_floor: float = 0.60
    warning_revise_threshold: int = 3
    approve_min_average_score: int = 75
    approve_min_agent_score: int = 60

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [e.strip().lower() for e in self.allowed_upload_extensions.split(",") if e.strip()]

    @property
    def outbound_allowed_hosts_list(self) -> list[str]:
        return [h.strip().lower() for h in self.outbound_allowed_hosts.split(",") if h.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
