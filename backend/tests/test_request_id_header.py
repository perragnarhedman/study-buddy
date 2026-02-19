from fastapi.testclient import TestClient

from app.main import app


def test_request_id_is_echoed_in_response_headers() -> None:
    client = TestClient(app)
    r = client.get("/health", headers={"X-Request-ID": "rid-123"})
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == "rid-123"

