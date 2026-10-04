from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import websocket
from app.api.routes import actions, chat, conversations, devices, health, tools, voice
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.security import get_current_user
from app.database.session import engine

setup_logging()
settings = get_settings()

VERSION = "0.2.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version=VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1 = APIRouter(prefix="/api/v1", dependencies=[Depends(get_current_user)])
api_v1.include_router(actions.router)
api_v1.include_router(chat.router)
api_v1.include_router(conversations.router)
api_v1.include_router(devices.router)
api_v1.include_router(tools.router)
api_v1.include_router(voice.router)

app.include_router(health.router)
app.include_router(api_v1)
app.include_router(websocket.router)


@app.get("/", tags=["health"])
async def root() -> dict[str, str]:
    """API information. The web client reads `name` from here, so renaming the
    assistant is a single change in settings."""
    return {
        "name": settings.app_name,
        "version": VERSION,
        "voice": settings.voice_engine,
        "docs": "/docs",
        "health": "/health",
    }
