import io
from pathlib import Path

from app.config import get_settings
from app.services.storage import request_upload_dir, sanitize_original_filename, save_upload
from tests.conftest import VALID_REQUEST_PAYLOAD


class _FakeUpload:
    def __init__(self, filename: str):
        self.filename = filename


def test_sanitize_strips_directory_components():
    assert sanitize_original_filename("../../etc/passwd") == "passwd"
    assert sanitize_original_filename("..\\..\\windows\\system32\\evil.txt") == "evil.txt"
    assert sanitize_original_filename("/abs/path/file.md") == "file.md"


def test_save_upload_with_traversal_filename_stays_inside_storage_dir(client):
    req = client.post("/api/requests", json=VALID_REQUEST_PAYLOAD).json()
    settings = get_settings()
    storage_root = Path(settings.storage_dir).resolve()

    malicious = _FakeUpload("../../../../evil.txt")
    original_filename, stored_filename, extension, size_bytes = save_upload(
        req["id"], malicious, b"malicious content"
    )

    expected_dir = request_upload_dir(req["id"]).resolve()
    written_path = (expected_dir / stored_filename).resolve()

    assert storage_root in written_path.parents
    assert written_path.parent == expected_dir
    # the traversal attempt never survives into the stored filename
    assert ".." not in stored_filename
    assert "/" not in stored_filename and "\\" not in stored_filename


def test_upload_endpoint_rejects_traversal_filename_without_escaping_storage(client):
    req = client.post("/api/requests", json=VALID_REQUEST_PAYLOAD).json()
    files = {"file": ("../../../../evil.md", io.BytesIO(b"payload"), "text/markdown")}
    resp = client.post(f"/api/requests/{req['id']}/documents", files=files)

    # multipart clients typically strip the path themselves, but even if a
    # path-like name reaches the server, storage.py must not honor it.
    assert resp.status_code in (201, 400)
    if resp.status_code == 201:
        doc = resp.json()
        assert ".." not in doc["original_filename"]

        settings = get_settings()
        storage_root = Path(settings.storage_dir).resolve()
        for path in storage_root.rglob("*"):
            if path.is_file():
                assert storage_root in path.resolve().parents
