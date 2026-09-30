"""Command bus: the brain asks a device agent to run something and waits.

Every invocation carries a `call_id`; the agent echoes it back in its result,
which wakes the waiting caller. A missing answer is a failure, never a success.
"""

import asyncio
import logging
import uuid
from typing import Any

from pydantic import BaseModel

from app.agents.manager import AgentManager, agent_manager

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 20.0


class CommandResult(BaseModel):
    ok: bool
    data: Any = None
    error: str | None = None
    # True when the agent checked the real state afterwards (e.g. the app is running).
    verified: bool = False


class DeviceOfflineError(Exception):
    pass


class CommandBus:
    def __init__(self, agents: AgentManager) -> None:
        self._agents = agents
        self._pending: dict[str, asyncio.Future[CommandResult]] = {}

    async def invoke(
        self,
        device_id: str,
        capability: str,
        arguments: dict[str, Any],
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> CommandResult:
        if not self._agents.is_connected(device_id):
            raise DeviceOfflineError(device_id)

        call_id = str(uuid.uuid4())
        future: asyncio.Future[CommandResult] = asyncio.get_running_loop().create_future()
        self._pending[call_id] = future
        try:
            await self._agents.send(
                device_id,
                {"type": "invoke", "call_id": call_id, "capability": capability, "arguments": arguments},
            )
            return await asyncio.wait_for(future, timeout)
        except TimeoutError:
            logger.warning("Device %s did not answer %s within %ss", device_id, capability, timeout)
            return CommandResult(ok=False, error=f"Device did not answer within {timeout:.0f}s")
        finally:
            self._pending.pop(call_id, None)

    def resolve(self, call_id: str, result: CommandResult) -> None:
        future = self._pending.get(call_id)
        if future is None or future.done():
            logger.warning("Result for unknown or expired call %s", call_id)
            return
        future.set_result(result)


command_bus = CommandBus(agent_manager)
