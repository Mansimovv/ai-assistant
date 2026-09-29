from typing import Any

from app.tools.base import Tool
from app.tools.examples import Echo, GetCurrentTime


class ToolNotFoundError(LookupError):
    pass


class ConfirmationRequiredError(Exception):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool[Any]] = {}

    def register(self, tool: Tool[Any]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool[Any]:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(name) from None

    def list_tools(self) -> list[Tool[Any]]:
        return list(self._tools.values())

    async def execute(self, name: str, arguments: dict[str, Any], *, confirmed: bool = False) -> Any:
        """Validate arguments and run a tool.

        Raises ToolNotFoundError, pydantic.ValidationError for invalid arguments,
        and ConfirmationRequiredError for dangerous tools run without confirmation.
        """
        tool = self.get(name)
        if tool.requires_confirmation and not confirmed:
            raise ConfirmationRequiredError(name)
        params = tool.parameters.model_validate(arguments)
        return await tool.execute(params)


def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(GetCurrentTime())
    registry.register(Echo())
    return registry
