import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app


def test_plan_week_returns_503_when_openai_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()

    import app.services.planning as planning_module

    async def fake_plan_week(*args, **kwargs) -> str:
        raise TimeoutError("read_timeout")

    monkeypatch.setattr(planning_module, "plan_week", fake_plan_week)

    client = TestClient(app)
    r = client.get("/plan/week", headers={"Authorization": f"Bearer {issue_session_token('u1')}"})
    assert r.status_code == 503


