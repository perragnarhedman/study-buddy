from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routes.auth_google import router as auth_google_router
from app.routes.chat import router as chat_router
from app.routes.classroom import router as classroom_router
from app.routes.health import router as health_router
from app.routes.plan import router as plan_router


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="Study Buddy API")
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


