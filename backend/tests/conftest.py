import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://buildgate:buildgate@db:5432/buildgate_test",
    ),
)

from app.config import get_settings  # noqa: E402
from app.db import models  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import embeddings, llm  # noqa: E402


class FakeEmbeddingProvider:
    """Deterministic fake embedding so tests never call Ollama."""

    name = "fake"

    def embed(self, texts):
        settings = get_settings()
        dim = settings.embedding_dim
        vectors = []
        for text_value in texts:
            seed = sum(ord(c) for c in text_value) or 1
            vectors.append([((seed * (i + 1)) % 97) / 97.0 for i in range(dim)])
        return vectors


@pytest.fixture(scope="session")
def storage_dir():
    path = tempfile.mkdtemp(prefix="buildgate_test_uploads_")
    os.environ["STORAGE_DIR"] = path
    get_settings.cache_clear()
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session")
def engine(storage_dir):
    settings = get_settings()
    eng = create_engine(settings.database_url)
    with eng.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    # Uses the app's real SessionLocal (same engine) rather than a
    # savepoint-wrapped connection, because ingestion runs as a background
    # task on its own session -- truncating after each test is what actually
    # cleans up writes from both the request session and the background
    # task's session.
    from app.db.session import SessionLocal as AppSessionLocal

    session = AppSessionLocal()
    yield session
    session.close()
    with engine.connect() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE audit_events, decisions, agent_reviews, "
                "document_chunks, documents, requests RESTART IDENTITY CASCADE"
            )
        )
        conn.commit()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    embeddings.set_embedding_provider(FakeEmbeddingProvider())
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    embeddings.reset_embedding_provider()


VALID_REQUEST_PAYLOAD = {
    "title": "Test request",
    "description": "A description",
    "business_reason": "Because reasons",
    "requested_deadline": "2026-12-31",
    "deadline_is_fixed": True,
}


class FakeLLMProvider:
    """Deterministic stand-in for Ollama.

    Returns whatever `queue` supplies, so a test can script schema-valid
    output, malformed output, or an outright failure without a model.
    """

    name = "fake"
    model = "fake-model"

    def __init__(self, responses=None, default=None):
        import threading

        self._lock = threading.Lock()
        # `responses` is consumed in order; `default` is what every remaining
        # call returns once it is exhausted. With a multi-agent board most tests
        # want one scripted outcome applied to every reviewer, which is what
        # `default` is for.
        self.responses = list(responses or [])
        self.default = default
        self.calls = []

    def generate_json(self, system, prompt, schema, attempt=1):
        # Agents run concurrently, so scripted responses need a lock.
        with self._lock:
            self.calls.append(
                {"system": system, "prompt": prompt, "schema": schema, "attempt": attempt}
            )
            nxt = self.responses.pop(0) if self.responses else self.default
        if nxt is None:
            raise AssertionError("FakeLLMProvider ran out of scripted responses")
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def valid_agent_payload(**overrides):
    """A schema-valid PRODUCT review; override any field per test."""
    payload = {
        "agent": "PRODUCT",
        "score": 72,
        # PASS rather than WARNING: with a multi-agent board, a WARNING from
        # every reviewer trips R3_MULTIPLE_WARNINGS, and most tests want the
        # quieter path where only the score keeps it below APPROVE.
        "status": "PASS",
        "confidence": 0.8,
        "summary": "The problem is evidenced but the success measure is vague.",
        "findings": [],
        "questions": ["How will success be measured?"],
        "required_actions": ["Define a success metric"],
        "assumptions": [],
        "critical_information_missing": False,
        "deadline_assessment": None,
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def fake_llm():
    provider = FakeLLMProvider()
    llm.set_llm_provider(provider)
    yield provider
    llm.reset_llm_provider()
