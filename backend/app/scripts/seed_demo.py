"""Creates the demo request and ingests the seeded demo documents.

Run with: docker compose exec api python -m app.scripts.seed_demo
"""
import datetime
import uuid
from pathlib import Path

from app.core.enums import AuditEventType
from app.db.models import Document, Request
from app.db.session import SessionLocal
from app.services.audit import record_event
from app.services.ingestion import process_document
from app.services.storage import request_upload_dir, sanitize_original_filename, validate_extension

DEMO_DOCS_DIR = Path("/data/demo")

DEMO_REQUEST = {
    "title": "Self-service customer data export button",
    "description": (
        "Add an 'Export My Data' button to the customer portal so enterprise "
        "admins can generate their own account/usage/billing export instead "
        "of emailing support."
    ),
    "business_reason": (
        "Support handles ~40 manual export requests per month at a 3-day "
        "turnaround; this is intended to cut that to self-service in minutes."
    ),
    "requested_deadline": datetime.date.today() + datetime.timedelta(days=21),
    "deadline_is_fixed": True,
    "requester": "Dana Whitfield",
    "department": "Customer Success",
    "expected_outcome": "80% reduction in manual export support tickets.",
    "target_users": "Enterprise portal admins (~1,200 accounts).",
    "priority": "High",
    "notes": "Leadership wants this announced at the Q3 customer webinar.",
}


def seed() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Request).filter(Request.title == DEMO_REQUEST["title"]).first()
        if existing:
            print(f"Demo request already exists: {existing.id}")
            return

        req = Request(**DEMO_REQUEST)
        db.add(req)
        db.commit()
        db.refresh(req)
        record_event(db, req.id, AuditEventType.REQUEST_CREATED, actor=req.requester, payload={"title": req.title})
        print(f"Created demo request {req.id}")

        for path in sorted(DEMO_DOCS_DIR.glob("*.md")):
            raw_bytes = path.read_bytes()
            original_filename = sanitize_original_filename(path.name)
            extension = validate_extension(original_filename)

            directory = request_upload_dir(str(req.id))
            stored_filename = f"{uuid.uuid4().hex}{extension}"
            (directory / stored_filename).write_bytes(raw_bytes)

            document = Document(
                request_id=req.id,
                original_filename=original_filename,
                stored_filename=stored_filename,
                extension=extension,
                size_bytes=len(raw_bytes),
            )
            db.add(document)
            db.commit()
            db.refresh(document)

            record_event(
                db,
                req.id,
                AuditEventType.DOCUMENT_UPLOADED,
                payload={"document_id": str(document.id), "filename": original_filename},
            )

            process_document(db, document.id)
            print(f"Ingested {original_filename} -> document {document.id}")

        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
