"""Tool contract.

A tool is one capability the assistant can use: a name and description the model
reads, a Pydantic model describing its parameters (exported as JSON Schema for
function calling), and `execute`.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.security import Permission


class ToolParameters(BaseModel):
    """Base for tool parameters. Unknown arguments are rejected, not ignored."""

    model_config = ConfigDict(extra="forbid")


class Tool[P: ToolParameters](ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    parameters: type[P]
    permission: ClassVar[Permission] = Permission.READ
    # Dangerous tools (deleting files, sending messages, running commands) set this
    # so the registry refuses to run them without explicit user confirmation.
    requires_confirmation: ClassVar[bool] = False

    @abstractmethod
    async def execute(self, params: P) -> Any:
        """Run the tool. The result must be JSON-serializable."""
