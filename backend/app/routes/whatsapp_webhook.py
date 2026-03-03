import hashlib
import hmac
import logging
import re
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.core.config import get_settings
from app.core.db import (
    consume_whatsapp_link_code,
    get_user_id_by_whatsapp_id,
    upsert_whatsapp_link,
    whatsapp_dedup_should_process,
)
from app.services.chat_core import send_chat
from app.services.planning import generate_weekly_plan_openai_required

router = APIRouter()
logger = logging.getLogger(__name__)


def _require_whatsapp_config() -> None:
    s = get_settings()
    missing = []
    if not s.whatsapp_access_token:
        missing.append("WHATSAPP_ACCESS_TOKEN")
    if not s.whatsapp_phone_number_id:
        missing.append("WHATSAPP_PHONE_NUMBER_ID")
    if missing:
        raise HTTPException(status_code=503, detail=f"WhatsApp not configured ({', '.join(missing)})")


def _verify_webhook_signature(*, body: bytes, signature_header: Optional[str]) -> None:
    """
    Meta sends: X-Hub-Signature-256: sha256=<hex(hmac_sha256(app_secret, body))>
    """
    s = get_settings()
    if not s.whatsapp_app_secret:
        raise HTTPException(status_code=503, detail="WhatsApp not configured (WHATSAPP_APP_SECRET)")
    expected = hmac.new(s.whatsapp_app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    expected_header = f"sha256={expected}"
    got = signature_header or ""
    if not hmac.compare_digest(got, expected_header):
        raise HTTPException(status_code=403, detail="Invalid signature")


async def _send_text(*, to_wa_id: str, text: str) -> None:
    _require_whatsapp_config()
    s = get_settings()

    # Conservative truncation (WhatsApp text max is higher, but keep a safe buffer).
    body_text = (text or "").strip()
    if len(body_text) > 3500:
        body_text = body_text[:3490].rstrip() + "…"

    url = f"https://graph.facebook.com/v21.0/{s.whatsapp_phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "text",
        "text": {"body": body_text},
    }
    headers = {"Authorization": f"Bearer {s.whatsapp_access_token}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        if r.status_code >= 300:
            logger.warning("whatsapp_send_failed status=%s body=%s", r.status_code, r.text[:500])


def _extract_first_text_message(payload: dict) -> Optional[tuple[str, str, str]]:
    """
    Return (wa_id, message_id, text_body) for the first text message found.
    """
    try:
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                for msg in value.get("messages") or []:
                    if msg.get("type") != "text":
                        continue
                    wa_id = str(msg.get("from") or "").strip()
                    message_id = str(msg.get("id") or "").strip()
                    text_body = str(((msg.get("text") or {}).get("body")) or "").strip()
                    if wa_id and message_id and text_body:
                        return wa_id, message_id, text_body
    except Exception:
        return None
    return None


@router.get("/whatsapp/webhook")
def whatsapp_webhook_verify(
    hub_mode: Optional[str] = Query(default=None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(default=None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(default=None, alias="hub.challenge"),
) -> Response:
    s = get_settings()
    if not s.whatsapp_verify_token:
        raise HTTPException(status_code=503, detail="WhatsApp not configured (WHATSAPP_VERIFY_TOKEN)")
    if hub_mode == "subscribe" and hub_verify_token == s.whatsapp_verify_token and hub_challenge:
        return Response(content=str(hub_challenge), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request) -> dict:
    body = await request.body()
    _verify_webhook_signature(body=body, signature_header=request.headers.get("X-Hub-Signature-256"))

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    extracted = _extract_first_text_message(payload)
    if not extracted:
        # Ignore non-text messages for v1.
        return {"status": "ignored"}

    wa_id, message_id, text_body = extracted
    if not whatsapp_dedup_should_process(message_id=message_id):
        return {"status": "duplicate_ignored"}

    # 1) Linking flow: user sends "LINK <code>"
    m = re.match(r"^\s*link\s+([0-9]{4,12})\s*$", text_body, flags=re.IGNORECASE)
    if m:
        code = m.group(1)
        user_id = consume_whatsapp_link_code(code=code)
        if not user_id:
            await _send_text(
                to_wa_id=wa_id,
                text="That connect code is invalid or expired. In StudyBuddy, generate a new WhatsApp connect code and send: LINK <code>.",
            )
            return {"status": "link_failed"}
        upsert_whatsapp_link(wa_id=wa_id, user_id=user_id)
        await _send_text(to_wa_id=wa_id, text="Connected. You can now chat with StudyBuddy here.")
        return {"status": "linked"}

    # 2) Normal chat: must already be linked.
    user_id = get_user_id_by_whatsapp_id(wa_id=wa_id)
    if not user_id:
        await _send_text(
            to_wa_id=wa_id,
            text="To connect StudyBuddy, open the app, generate a WhatsApp connect code, then send: LINK <code>.",
        )
        return {"status": "unlinked"}

    # Reuse the same backend path as iOS by calling the existing handler with a server-built plan.
    try:
        plan, _meta = await generate_weekly_plan_openai_required(user_id=user_id)
        resp = await send_chat(user_id=user_id, user_message=text_body, current_plan=plan)
        await _send_text(to_wa_id=wa_id, text=resp.assistant_message.text)
        return {"status": "ok"}
    except HTTPException as e:
        if e.status_code in (502, 503):
            await _send_text(to_wa_id=wa_id, text="I’m having trouble right now. Please try again in a minute.")
            return {"status": "backend_unavailable"}
        raise

