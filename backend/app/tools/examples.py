from datetime import datetime
from typing import Any

from pydantic import Field

from app.tools.base import Tool, ToolParameters


class GetCurrentTime(Tool[ToolParameters]):
    name = "get_current_time"
    description = "Get the current date and time on the server."
    parameters = ToolParameters

    async def execute(self, params: ToolParameters) -> dict[str, Any]:
        now = datetime.now().astimezone()
        return {"iso": now.isoformat(), "timezone": now.tzname()}


class EchoParameters(ToolParameters):
    text: str = Field(description="Text to return.")


class Echo(Tool[EchoParameters]):
    name = "echo"
    description = "Return the given text unchanged. Useful for testing the tool pipeline."
    parameters = EchoParameters

    async def execute(self, params: EchoParameters) -> dict[str, Any]:
        return {"text": params.text}
