"""FastAPI dependency providers. Tests override these to swap implementations."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.manager import agent_manager
from app.ai.router import AIRouter
from app.ai.service import AIService, OpenAIService
from app.core.config import get_settings
from app.database.session import get_session
from app.devices.manager import DeviceManager
from app.tools.registry import ToolRegistry, create_default_registry


@lru_cache
def get_ai_service() -> AIService:
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
    return OpenAIService(api_key=api_key, model=settings.openai_model)


def get_ai_router(ai: Annotated[AIService, Depends(get_ai_service)]) -> AIRouter:
    return AIRouter(ai)


@lru_cache
def get_tool_registry() -> ToolRegistry:
    return create_default_registry()


def get_device_manager(session: Annotated[AsyncSession, Depends(get_session)]) -> DeviceManager:
    return DeviceManager(session, agent_manager)
