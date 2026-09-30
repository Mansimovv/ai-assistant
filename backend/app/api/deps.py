"""FastAPI dependency providers. Tests override these to swap implementations."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.bus import command_bus
from app.agents.manager import agent_manager
from app.ai.assistant import Assistant
from app.ai.confirmations import PendingActions, pending_actions
from app.ai.router import AIRouter
from app.ai.service import AIService, OpenAIService
from app.ai.voice import VoiceService
from app.core.config import Settings, get_settings
from app.database.session import get_session
from app.devices.actions import DeviceActions
from app.devices.manager import DeviceManager
from app.memory.conversations import ConversationService
from app.tools.registry import ToolRegistry, create_default_registry

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@lru_cache
def get_ai_service() -> AIService:
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
    return OpenAIService(api_key=api_key, model=settings.openai_model)


@lru_cache
def get_voice_service() -> VoiceService:
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
    return VoiceService(
        api_key=api_key,
        model=settings.realtime_model,
        voice=settings.realtime_voice,
        transcribe_model=settings.realtime_transcribe_model,
        language=settings.voice_language,
    )


@lru_cache
def get_tool_registry() -> ToolRegistry:
    return create_default_registry()


def get_device_actions() -> DeviceActions:
    return DeviceActions(agent_manager, command_bus)


def get_device_manager(session: SessionDep) -> DeviceManager:
    return DeviceManager(session, agent_manager)


def get_conversations(session: SessionDep) -> ConversationService:
    return ConversationService(session)


def get_ai_router(
    ai: Annotated[AIService, Depends(get_ai_service)],
    tools: Annotated[ToolRegistry, Depends(get_tool_registry)],
    devices: Annotated[DeviceActions, Depends(get_device_actions)],
) -> AIRouter:
    return AIRouter(ai, tools, devices)


def get_pending_actions() -> PendingActions:
    return pending_actions


def get_assistant(
    router: Annotated[AIRouter, Depends(get_ai_router)],
    conversations: Annotated[ConversationService, Depends(get_conversations)],
    devices: Annotated[DeviceManager, Depends(get_device_manager)],
    actions: Annotated[DeviceActions, Depends(get_device_actions)],
    pending: Annotated[PendingActions, Depends(get_pending_actions)],
    settings: SettingsDep,
) -> Assistant:
    return Assistant(
        router, conversations, devices, actions, pending, settings.app_name, settings.owner_name
    )


AssistantDep = Annotated[Assistant, Depends(get_assistant)]
ConversationsDep = Annotated[ConversationService, Depends(get_conversations)]
DeviceManagerDep = Annotated[DeviceManager, Depends(get_device_manager)]
DeviceActionsDep = Annotated[DeviceActions, Depends(get_device_actions)]
RegistryDep = Annotated[ToolRegistry, Depends(get_tool_registry)]
VoiceServiceDep = Annotated[VoiceService, Depends(get_voice_service)]
