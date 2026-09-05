from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.services.embeddings import OllamaEmbeddingProvider, get_embedding_provider
from app.services.http_client import counters

router = APIRouter(prefix="/api")


@router.get("/runtime")
def runtime(db: Session = Depends(get_db)):
    settings = get_settings()

    db_connected = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_connected = False

    ollama_probe = OllamaEmbeddingProvider(settings.ollama_host, settings.embedding_model)
    ollama_reachable = ollama_probe.ping()

    active_provider = get_embedding_provider()

    return {
        "mode": "local",
        "database": {"connected": db_connected},
        "ollama": {"reachable": ollama_reachable, "host": settings.ollama_host},
        "embedding": {
            "configured_provider": settings.embedding_provider,
            "active_provider": active_provider.name,
            "model": settings.embedding_model
            if active_provider.name == "ollama"
            else settings.sentence_transformers_model,
        },
        "outbound_http": {
            **counters.as_dict(),
            "allowed_hosts": settings.outbound_allowed_hosts_list,
        },
        "storage_dir": settings.storage_dir,
    }
