"""Server side of device agents.

A device agent is a small program running on a device (see /agents/mac in the
repository root) that keeps a WebSocket open to the backend. The backend sends
it commands and receives results over that socket.
"""

from typing import Any

from fastapi import WebSocket


class AgentConnection:
    def __init__(self, device_id: str, websocket: WebSocket) -> None:
        self.device_id = device_id
        self._websocket = websocket

    async def send(self, message: dict[str, Any]) -> None:
        await self._websocket.send_json(message)
