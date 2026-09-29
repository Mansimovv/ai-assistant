import logging
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from app.agents.base import AgentConnection
from app.agents.manager import agent_manager
from app.api.deps import get_device_manager
from app.devices.manager import DeviceManager
from app.schemas.devices import RegisterMessage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/devices")
async def device_socket(websocket: WebSocket, devices: Annotated[DeviceManager, Depends(get_device_manager)]) -> None:
    """Real-time channel for device agents.

    Protocol (JSON messages):
        agent  -> {"type": "register", "device": {"id": "macbook", "name": "MacBook", "type": "mac"}}
        server -> {"type": "registered"}
    The socket then stays open; the device is online until it disconnects.
    Commands and their results will travel over this socket.
    """
    await websocket.accept()
    try:
        message = RegisterMessage.model_validate_json(await websocket.receive_text())
    except ValidationError:
        await websocket.close(status.WS_1008_POLICY_VIOLATION, "First message must be a valid register message")
        return
    except WebSocketDisconnect:
        return

    device = message.device
    await devices.register(device)
    connection = AgentConnection(device.id, websocket)
    agent_manager.connect(connection)
    logger.info("Device %s connected", device.id)
    try:
        await websocket.send_json({"type": "registered"})
        async for _ in websocket.iter_text():
            # Command results and device events will be handled here.
            logger.debug("Message from device %s", device.id)
    finally:
        agent_manager.disconnect(connection)
        await devices.mark_seen(device.id)
        logger.info("Device %s disconnected", device.id)
