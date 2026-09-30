"""Device capabilities as tools the model can call.

Only capabilities of *online* devices become tools, so the model cannot call
something that has no chance of running.
"""

import logging
import time

from pydantic import ValidationError

from app.agents.bus import DEFAULT_TIMEOUT_SECONDS, CommandBus, CommandResult, DeviceOfflineError
from app.agents.manager import AgentManager
from app.ai.service import ToolSpec
from app.devices.capabilities import CAPABILITIES, Capability, Risk

logger = logging.getLogger(__name__)


class DeviceActions:
    def __init__(self, agents: AgentManager, bus: CommandBus, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._agents = agents
        self._bus = bus
        self._timeout = timeout

    def specs(self) -> list[ToolSpec]:
        specs: dict[str, ToolSpec] = {}
        for connection in self._agents.connections():
            for name in connection.capabilities:
                capability = CAPABILITIES.get(name)
                if capability is None:
                    continue  # agent knows a capability this backend doesn't
                tool_name = self._tool_name(connection.device_type, capability.name)
                specs[tool_name] = ToolSpec(
                    name=tool_name,
                    description=f"{capability.description} Runs on {connection.device_name}.",
                    parameters=capability.parameters.model_json_schema(),
                )
        return list(specs.values())

    def knows(self, tool_name: str) -> bool:
        return self._resolve(tool_name) is not None

    def risk(self, tool_name: str) -> Risk:
        resolved = self._resolve(tool_name)
        return resolved[1].risk if resolved else Risk.HIGH

    async def execute(self, tool_name: str, arguments: dict) -> CommandResult:
        resolved = self._resolve(tool_name)
        if resolved is None:
            return CommandResult(ok=False, error=f"No online device provides {tool_name}")
        device_ids, capability = resolved

        if len(device_ids) > 1:
            return CommandResult(
                ok=False,
                error=f"Several devices provide {tool_name}: {', '.join(device_ids)}. Ask the user which one.",
            )

        try:
            params = capability.parameters.model_validate(arguments)
        except ValidationError as exc:
            return CommandResult(ok=False, error=f"Invalid arguments: {exc.errors(include_url=False)}")

        started = time.monotonic()
        try:
            result = await self._bus.invoke(device_ids[0], capability.name, params.model_dump(), self._timeout)
        except DeviceOfflineError:
            return CommandResult(ok=False, error="The device went offline")
        logger.info(
            "%s on %s -> ok=%s (%dms)", capability.name, device_ids[0], result.ok, (time.monotonic() - started) * 1000
        )
        return result

    def _resolve(self, tool_name: str) -> tuple[list[str], Capability] | None:
        for connection in self._agents.connections():
            for name in connection.capabilities:
                capability = CAPABILITIES.get(name)
                if capability and self._tool_name(connection.device_type, name) == tool_name:
                    device_ids = [
                        other.device_id
                        for other in self._agents.connections()
                        if other.device_type == connection.device_type and name in other.capabilities
                    ]
                    return device_ids, capability
        return None

    @staticmethod
    def _tool_name(device_type: str, capability: str) -> str:
        return f"{device_type}_{capability}"
