from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import websocket
from app.api.routes import chat, devices, health, tools
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.security import get_current_user
from app.database.session import engine

setup_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(title="Personal AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1 = APIRouter(prefix="/api/v1", dependencies=[Depends(get_current_user)])
api_v1.include_router(chat.router)
api_v1.include_router(devices.router)
api_v1.include_router(tools.router)

app.include_router(health.router)
app.include_router(api_v1)
app.include_router(websocket.router)


@app.get("/", tags=["health"])
async def root() -> dict[str, str]:
    return {"name": "Personal AI", "version": app.version, "docs": "/docs", "health": "/health"}
