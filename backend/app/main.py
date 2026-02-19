from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from uuid import uuid4
import logging

from app.core.config import get_settings
from app.core.logging import configure_logging, reset_request_id, set_request_id
from app.routes.auth_google import router as auth_google_router
from app.routes.chat import router as chat_router
from app.routes.classroom import router as classroom_router
from app.routes.health import router as health_router
from app.routes.plan import router as plan_router


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    logger = logging.getLogger(__name__)

    app = FastAPI(title="Study Buddy API")

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        """
        Minimal observability: attach a request id to every response and log it for errors.
        """
        rid = request.headers.get("X-Request-ID") or uuid4().hex[:12]
        token = set_request_id(rid)
        try:
            response: Response = await call_next(request)
        except Exception:
            # High-level only; avoid logging secrets.
            logger.exception("request_error path=%s method=%s", request.url.path, request.method)
            raise
        finally:
            reset_request_id(token)
        response.headers["X-Request-ID"] = rid
        return response
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(plan_router)
    app.include_router(auth_google_router)
    app.include_router(classroom_router)
    return app


app = create_app()


