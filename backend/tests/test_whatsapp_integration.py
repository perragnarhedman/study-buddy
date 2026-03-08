import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.core.db import create_whatsapp_link_code, get_user_id_by_whatsapp_id, upsert_whatsapp_link
from app.main import app
from app.models.schemas import ChatMessage, ChatSendResponse, PlanItem, WeeklyPlan


def _sign(*, secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _wa_payload(*, wa_id: str, message_id: str, text: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": message_id,
                                    "timestamp": "123",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ]
                        },
                    }
                ],
            }
        ],
    }


def test_whatsapp_link_code_requires_auth(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    client = TestClient(app)

    r = client.post("/whatsapp/link/code")
    assert r.status_code == 401


def test_whatsapp_link_code_returns_numeric_code(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    client = TestClient(app)

    token = issue_session_token("u1")
    r = client.post("/whatsapp/link/code", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("code"), str)
    assert data["code"].isdigit()
    assert len(data["code"]) == 6
    assert isinstance(data.get("expires_at"), int)


def test_whatsapp_webhook_verify_get(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "vt")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    client = TestClient(app)

    r = client.get("/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=vt&hub.challenge=123")
    assert r.status_code == 200
    assert r.text == "123"


def test_whatsapp_webhook_rejects_invalid_signature(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    client = TestClient(app)

    body = json.dumps(_wa_payload(wa_id="1555", message_id="m1", text="Hi"), separators=(",", ":")).encode("utf-8")
    r = client.post(
        "/whatsapp/webhook",
        data=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=bad"},
    )
    assert r.status_code == 403


def test_whatsapp_webhook_link_flow(monkeypatch, tmp_path) -> None:
    import app.routes.whatsapp_webhook as wa_route

    sent: list[str] = []

    async def fake_send_text(*, to_wa_id: str, text: str) -> None:
        sent.append(text)

    monkeypatch.setattr(wa_route, "_send_text", fake_send_text)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "pnid")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    client = TestClient(app)

    code, _exp = create_whatsapp_link_code(user_id="u1", ttl_seconds=600, code_len=6)
    payload = _wa_payload(wa_id="15551234567", message_id="m1", text=f"LINK {code}")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    r = client.post(
        "/whatsapp/webhook",
        data=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(secret="secret", body=body)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "linked"
    assert get_user_id_by_whatsapp_id(wa_id="15551234567") == "u1"
    assert any("Connected" in s for s in sent)


def test_whatsapp_webhook_unlinked_sender_gets_instructions(monkeypatch, tmp_path) -> None:
    import app.routes.whatsapp_webhook as wa_route

    sent: list[str] = []

    async def fake_send_text(*, to_wa_id: str, text: str) -> None:
        sent.append(text)

    monkeypatch.setattr(wa_route, "_send_text", fake_send_text)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "pnid")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    client = TestClient(app)

    payload = _wa_payload(wa_id="15551230000", message_id="m1", text="Hello")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    r = client.post(
        "/whatsapp/webhook",
        data=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(secret="secret", body=body)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "unlinked"
    assert any("LINK <code>" in s for s in sent)


def test_whatsapp_webhook_linked_routes_through_chat_core(monkeypatch, tmp_path) -> None:
    import app.routes.whatsapp_webhook as wa_route

    sent: list[str] = []

    async def fake_send_text(*, to_wa_id: str, text: str) -> None:
        sent.append(text)

    async def fake_generate_weekly_plan(*, user_id: str):
        return (
            WeeklyPlan(
                weekStart="2026-01-05",
                items=[PlanItem(id="p1", title="Do thing", dueDate=None, estimatedMinutes=10, status="todo")],
            ),
            {"meta": "ok"},
        )

    async def fake_send_chat(
        *,
        user_id: str,
        user_message: str,
        current_plan: WeeklyPlan,
        export_source=None,
    ) -> ChatSendResponse:
        assert user_id == "u1"
        assert user_message == "Hi"
        assert export_source is not None
        assert export_source["channel"] == "whatsapp"
        return ChatSendResponse(
            assistant_message=ChatMessage(id="a1", role="assistant", text="Hello from StudyBuddy", timestamp="t"),
            best_next_action=None,
        )

    monkeypatch.setattr(wa_route, "_send_text", fake_send_text)
    monkeypatch.setattr(wa_route, "generate_weekly_plan_openai_required", fake_generate_weekly_plan)
    monkeypatch.setattr(wa_route, "send_chat", fake_send_chat)

    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "pnid")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    client = TestClient(app)

    upsert_whatsapp_link(wa_id="15551239999", user_id="u1")
    payload = _wa_payload(wa_id="15551239999", message_id="m1", text="Hi")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    r = client.post(
        "/whatsapp/webhook",
        data=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(secret="secret", body=body)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert sent == ["Hello from StudyBuddy"]

