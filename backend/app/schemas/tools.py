from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.security import Permission
from app.devices.capabilities import Risk


class ToolInfo(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    risk: Risk
    target: Literal["backend", "device"]
    permission: Permission | None = None
    requires_confirmation: bool = False


class ToolExecuteRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class ToolExecuteResponse(BaseModel):
    tool: str
    result: Any
