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
