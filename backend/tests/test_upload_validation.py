import io
import time

from tests.conftest import VALID_REQUEST_PAYLOAD


def _create_request(client):
    return client.post("/api/requests", json=VALID_REQUEST_PAYLOAD).json()


def _wait_for_document_status(client, request_id, document_id, timeout=10):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        resp = client.get(f"/api/requests/{request_id}/documents/{document_id}")
        last = resp.json()
        if last["status"] in ("READY", "PROCESSING_FAILED"):
            return last
        time.sleep(0.1)
    return last


def test_upload_valid_markdown_is_accepted_and_processed(client):
    req = _create_request(client)
    files = {"file": ("notes.md", io.BytesIO(b"# Title\n\nSome body text."), "text/markdown")}
    resp = client.post(f"/api/requests/{req['id']}/documents", files=files)
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["original_filename"] == "notes.md"

    final = _wait_for_document_status(client, req["id"], doc["id"])
    assert final["status"] == "READY"


def test_upload_disallowed_extension_is_rejected(client):
    req = _create_request(client)
    files = {"file": ("malware.exe", io.BytesIO(b"not really an exe"), "application/octet-stream")}
    resp = client.post(f"/api/requests/{req['id']}/documents", files=files)
    assert resp.status_code == 400


def test_upload_oversized_file_is_rejected(client):
    req = _create_request(client)
    big_content = b"a" * (11 * 1024 * 1024)  # 11MB > 10MB cap
    files = {"file": ("big.txt", io.BytesIO(big_content), "text/plain")}
    resp = client.post(f"/api/requests/{req['id']}/documents", files=files)
    assert resp.status_code == 413


def test_upload_empty_file_is_rejected(client):
    req = _create_request(client)
    files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
    resp = client.post(f"/api/requests/{req['id']}/documents", files=files)
    assert resp.status_code == 400


def test_upload_generates_internal_storage_name(client):
    req = _create_request(client)
    files = {"file": ("Weird Name!!.md", io.BytesIO(b"content"), "text/markdown")}
    resp = client.post(f"/api/requests/{req['id']}/documents", files=files)
    assert resp.status_code == 201
    doc = resp.json()
    # disallowed characters are sanitized out of the display filename
    assert doc["original_filename"] == "Weird Name__.md"
    assert doc["extension"] == ".md"


def test_extraction_failure_marks_document_failed_not_request(client):
    req = _create_request(client)

    from app.services import embeddings

    class BrokenProvider:
        name = "broken"

        def embed(self, texts):
            raise RuntimeError("embedding backend unavailable")

    embeddings.set_embedding_provider(BrokenProvider())

    files = {"file": ("notes.md", io.BytesIO(b"content that will fail to embed"), "text/markdown")}
    resp = client.post(f"/api/requests/{req['id']}/documents", files=files)
    assert resp.status_code == 201
    doc = resp.json()

    final = _wait_for_document_status(client, req["id"], doc["id"])
    assert final["status"] == "PROCESSING_FAILED"
    assert final["failure_reason"]

    request_resp = client.get(f"/api/requests/{req['id']}")
    assert request_resp.status_code == 200
