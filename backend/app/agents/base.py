"""Server side of device agents.

A device agent is a program running on a device (see /agents/mac in the
repository root) that keeps a WebSocket open to the backend. It announces what
it can do, receives commands and returns results over that socket.
"""

from typing import Any

from fastapi import WebSocket


class AgentConnection:
    def __init__(
        self,
        device_id: str,
        device_name: str,
        device_type: str,
        capabilities: list[str],
        websocket: WebSocket,
        apps: list[str] | None = None,
    ) -> None:
        self.device_id = device_id
        self.device_name = device_name
        self.device_type = device_type
        self.capabilities = capabilities
        self.apps = apps or []
        self._websocket = websocket

    async def send(self, message: dict[str, Any]) -> None:
        await self._websocket.send_json(message)
