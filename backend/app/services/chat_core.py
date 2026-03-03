from app.core.auth import AuthContext
from app.models.schemas import ChatSendRequest, ChatSendResponse, WeeklyPlan
from app.routes.chat import chat_send


async def send_chat(*, user_id: str, user_message: str, current_plan: WeeklyPlan) -> ChatSendResponse:
    """
    Shared entrypoint for non-iOS channels (e.g. WhatsApp) that want to reuse the
    exact same behavior as the /chat/send API.
    """
    return await chat_send(
        ChatSendRequest(user_message=user_message, current_plan=current_plan),
        AuthContext(user_id=user_id),
    )

