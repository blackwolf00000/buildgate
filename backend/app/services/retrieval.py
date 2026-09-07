"""Semantic retrieval over a request's document chunks.

Below the small-corpus threshold, similarity search is skipped entirely and
every chunk is returned -- vector search over a five-document demo set can
silently miss the one policy line an agent (or a human) needs, so below
~60 chunks we just hand back the whole corpus, scored for display purposes.
"""
import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Document, DocumentChunk


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb)) or 1e-9
    return float(np.dot(va, vb) / denom)


def retrieve(db: Session, request_id, query_embedding: list[float], top_k: int | None = None):
    """Returns a list of (DocumentChunk, Document, score) tuples, best first."""
    settings = get_settings()
    top_k = top_k or settings.retrieval_top_k

    all_chunks = (
        db.query(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(DocumentChunk.request_id == request_id)
        .all()
    )

    if len(all_chunks) < settings.retrieval_small_corpus_threshold:
        scored = [
            (chunk, doc, _cosine_similarity(query_embedding, chunk.embedding))
            for chunk, doc in all_chunks
        ]
        scored.sort(key=lambda item: item[2], reverse=True)
        # Still ranked over the whole corpus rather than by vector search, so
        # the small-corpus guarantee holds -- nothing is excluded before
        # scoring. The cap then keeps the prompt small enough to review on CPU
        # in reasonable time. Set retrieval_max_chunks_per_agent to 0 to
        # restore the original "pass everything" behaviour.
        cap = settings.retrieval_max_chunks_per_agent
        return scored[:cap] if cap else scored

    rows = (
        db.query(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(DocumentChunk.request_id == request_id)
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
        .all()
    )
    return [
        (chunk, doc, _cosine_similarity(query_embedding, chunk.embedding))
        for chunk, doc in rows
    ]


def evidence_id_for(document_id, chunk_index: int) -> str:
    return f"DOC-{document_id}-CHUNK-{chunk_index}"
