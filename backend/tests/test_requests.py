from tests.conftest import VALID_REQUEST_PAYLOAD


def test_create_request_succeeds(client):
    resp = client.post("/api/requests", json=VALID_REQUEST_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == VALID_REQUEST_PAYLOAD["title"]
    assert body["deadline_is_fixed"] is True
    assert body["status"] == "DRAFT"


def test_create_request_missing_deadline_is_fixed_returns_422(client):
    payload = dict(VALID_REQUEST_PAYLOAD)
    del payload["deadline_is_fixed"]
    resp = client.post("/api/requests", json=payload)
    assert resp.status_code == 422


def test_create_request_missing_required_field_returns_422(client):
    payload = dict(VALID_REQUEST_PAYLOAD)
    del payload["business_reason"]
    resp = client.post("/api/requests", json=payload)
    assert resp.status_code == 422


def test_list_and_get_request_roundtrip(client):
    created = client.post("/api/requests", json=VALID_REQUEST_PAYLOAD).json()

    listing = client.get("/api/requests")
    assert listing.status_code == 200
    assert any(r["id"] == created["id"] for r in listing.json())

    fetched = client.get(f"/api/requests/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


def test_get_unknown_request_returns_404(client):
    resp = client.get("/api/requests/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_request_created_emits_audit_event(client):
    created = client.post("/api/requests", json=VALID_REQUEST_PAYLOAD).json()
    audit = client.get(f"/api/requests/{created['id']}/audit")
    assert audit.status_code == 200
    event_types = [e["event_type"] for e in audit.json()]
    assert "REQUEST_CREATED" in event_types


def test_reopen_request_via_patch(client):
    created = client.post("/api/requests", json=VALID_REQUEST_PAYLOAD).json()
    resp = client.patch(f"/api/requests/{created['id']}", json={"title": "Updated title"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated title"
