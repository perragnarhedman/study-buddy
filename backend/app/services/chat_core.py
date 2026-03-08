from __future__ import annotations

from app.core.auth import AuthContext
from app.models.schemas import ChatSendRequest, ChatSendResponse, WeeklyPlan
from app.routes.chat import _chat_send_impl


async def send_chat(
    *,
    user_id: str,
    user_message: str,
    current_plan: WeeklyPlan,
    export_source: dict[str, str] | None = None,
) -> ChatSendResponse:
    """
    Shared entrypoint for non-iOS channels (e.g. WhatsApp) that want to reuse the
    exact same behavior as the /chat/send API.
    """
    return await _chat_send_impl(
        ChatSendRequest(user_message=user_message, current_plan=current_plan),
        ctx=AuthContext(
            user_id=user_id,
            export_source=export_source or {"channel": "backend_internal", "transport": "internal", "route": "chat_core"},
        ),
        request=None,
        client_channel=None,
        client_platform=None,
        app_version=None,
        app_build=None,
    )

