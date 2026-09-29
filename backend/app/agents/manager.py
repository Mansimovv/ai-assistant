from typing import Any

from app.agents.base import AgentConnection


class AgentManager:
    """Tracks which device agents are connected right now.

    Connections live in memory, so this works with a single backend process.
    Running several workers would need a shared channel such as Redis pub/sub.
    """

    def __init__(self) -> None:
        self._connections: dict[str, AgentConnection] = {}

    def connect(self, connection: AgentConnection) -> None:
        self._connections[connection.device_id] = connection

    def disconnect(self, connection: AgentConnection) -> None:
        # If the device already reconnected, keep the newer connection.
        if self._connections.get(connection.device_id) is connection:
            del self._connections[connection.device_id]

    def is_connected(self, device_id: str) -> bool:
        return device_id in self._connections

    async def send(self, device_id: str, message: dict[str, Any]) -> None:
        connection = self._connections.get(device_id)
        if connection is None:
            raise LookupError(f"Device {device_id!r} is not connected")
        await connection.send(message)


agent_manager = AgentManager()
