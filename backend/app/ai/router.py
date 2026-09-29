from app.ai.prompts import SYSTEM_PROMPT
from app.ai.service import AIService, ChatMessage


class AIRouter:
    """Entry point for every user message.

    Today every message is answered directly by the model. With function
    calling, this is where a message is classified and, when it needs actions,
    handed to the Planner, whose steps run through the ToolRegistry:

        message -> AIRouter -> Planner -> tool selection -> tool execution -> response
    """

    def __init__(self, ai: AIService) -> None:
        self._ai = ai

    async def handle(self, message: str) -> str:
        return await self._ai.complete(
            [
                ChatMessage(role="system", content=SYSTEM_PROMPT),
                ChatMessage(role="user", content=message),
            ]
        )
