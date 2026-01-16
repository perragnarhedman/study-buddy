from fastapi.testclient import TestClient

from app.main import app


def test_classroom_assignments_returns_401_when_unauthenticated() -> None:
    client = TestClient(app)
    r = client.get("/classroom/assignments")
    assert r.status_code == 401


