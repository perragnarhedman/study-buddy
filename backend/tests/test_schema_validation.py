from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import WeeklyPlan


def test_weekly_plan_schema() -> None:
    client = TestClient(app)
    r = client.get("/plan/week")
    assert r.status_code == 200
    WeeklyPlan.model_validate(r.json())


