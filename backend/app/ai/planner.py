"""Planning: turning a request into tool calls.

Not wired in yet. It arrives with OpenAI function calling, when AIRouter hands
requests that need actions to a Planner and runs the resulting steps through
the ToolRegistry.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    steps: list[PlanStep]


class Planner(ABC):
    @abstractmethod
    async def plan(self, message: str) -> Plan:
        """Break a user request into tool calls."""
