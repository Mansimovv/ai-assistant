from typing import Any

from pydantic import BaseModel, Field

from app.core.security import Permission


class ToolInfo(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    permission: Permission
    requires_confirmation: bool


class ToolExecuteRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class ToolExecuteResponse(BaseModel):
    tool: str
    result: Any
