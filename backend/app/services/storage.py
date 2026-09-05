"""Upload safety: extension/size validation, filename sanitization, and
storage under generated internal names so a hostile original filename can
never influence a filesystem path (no path traversal, no overwrite, no
execution of uploaded content).
"""
import os
import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings


class UploadValidationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def sanitize_original_filename(filename: str) -> str:
    """Keep only a safe display name -- strips any path component and
    disallowed characters. Never used to build a filesystem path.
    """
    name = os.path.basename(filename or "")
    name = name.replace("\\", "_").replace("/", "_")
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip()
    return name or "upload"


def validate_extension(filename: str) -> str:
    settings = get_settings()
    ext = Path(filename or "").suffix.lower()
    if ext not in settings.allowed_extensions_list:
        allowed = ", ".join(settings.allowed_extensions_list)
        raise UploadValidationError(
            f"File extension '{ext}' is not allowed. Allowed: {allowed}", status_code=400
        )
    return ext


def request_upload_dir(request_id: str) -> Path:
    settings = get_settings()
    safe_request_id = str(uuid.UUID(str(request_id)))
    directory = Path(settings.storage_dir) / safe_request_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_upload(request_id: str, upload: UploadFile, raw_bytes: bytes) -> tuple[str, str, str, int]:
    """Validates and persists an uploaded file.

    Returns (original_filename, stored_filename, extension, size_bytes).
    """
    settings = get_settings()

    original_filename = sanitize_original_filename(upload.filename or "")
    extension = validate_extension(original_filename)

    size_bytes = len(raw_bytes)
    if size_bytes > settings.max_upload_bytes:
        raise UploadValidationError(
            f"File exceeds the {settings.max_upload_mb}MB upload limit", status_code=413
        )
    if size_bytes == 0:
        raise UploadValidationError("Uploaded file is empty", status_code=400)

    stored_filename = f"{uuid.uuid4().hex}{extension}"
    directory = request_upload_dir(request_id)
    destination = directory / stored_filename

    # Defense in depth: the destination must resolve to inside the request's
    # upload directory, even though stored_filename is always generated.
    if directory.resolve() not in destination.resolve().parents:
        raise UploadValidationError("Invalid upload path", status_code=400)

    with open(destination, "wb") as f:
        f.write(raw_bytes)

    return original_filename, stored_filename, extension, size_bytes


def read_document_text(request_id: str, stored_filename: str) -> str:
    directory = request_upload_dir(request_id)
    path = directory / stored_filename
    if directory.resolve() not in path.resolve().parents:
        raise UploadValidationError("Invalid document path", status_code=400)
    return path.read_text(encoding="utf-8", errors="replace")
