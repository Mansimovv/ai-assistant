import logging
import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from app.agents.base import AgentConnection
from app.agents.bus import CommandResult, command_bus
from app.agents.manager import agent_manager
from app.api.deps import DeviceManagerDep, SettingsDep
from app.devices.capabilities import CAPABILITIES
from app.schemas.devices import RegisterMessage, ResultMessage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/devices")
async def device_socket(websocket: WebSocket, devices: DeviceManagerDep, settings: SettingsDep) -> None:
    """Real-time channel for device agents.

    Protocol (JSON messages):
        agent  -> {"type": "register", "device": {"id", "name", "type"},
                   "capabilities": ["open_app", ...], "token": "..."}
        server -> {"type": "registered", "capabilities": [...accepted...]}
        server -> {"type": "invoke", "call_id": "...", "capability": "open_app", "arguments": {...}}
        agent  -> {"type": "result", "call_id": "...", "ok": true, "data": {...}, "verified": true}

    The device counts as online exactly while this socket is open.
    """
    await websocket.accept()
    try:
        message = RegisterMessage.model_validate_json(await websocket.receive_text())
    except ValidationError:
        await websocket.close(status.WS_1008_POLICY_VIOLATION, "First message must be a valid register message")
        return
    except WebSocketDisconnect:
        return

    expected = settings.agent_token.get_secret_value() if settings.agent_token else None
    if expected is not None and not (message.token and secrets.compare_digest(message.token, expected)):
        logger.warning("Rejected agent %s: invalid token", message.device.id)
        await websocket.close(status.WS_1008_POLICY_VIOLATION, "Invalid agent token")
        return

    device = message.device
    accepted = [name for name in message.capabilities if name in CAPABILITIES]
    ignored = set(message.capabilities) - set(accepted)
    if ignored:
        logger.warning("Device %s announced unknown capabilities: %s", device.id, sorted(ignored))

    await devices.register(device)
    connection = AgentConnection(device.id, device.name, device.type, accepted, websocket, message.apps)
    agent_manager.connect(connection)
    logger.info(
        "Device %s connected with capabilities: %s (%d apps)", device.id, accepted, len(message.apps)
    )
    try:
        await websocket.send_json({"type": "registered", "capabilities": accepted})
        async for raw in websocket.iter_text():
            _handle_agent_message(device.id, raw)
    finally:
        agent_manager.disconnect(connection)
        await devices.mark_seen(device.id)
        logger.info("Device %s disconnected", device.id)


def _handle_agent_message(device_id: str, raw: str) -> None:
    try:
        message = ResultMessage.model_validate_json(raw)
    except ValidationError:
        logger.warning("Ignoring unexpected message from device %s", device_id)
        return
    command_bus.resolve(
        message.call_id,
        CommandResult(ok=message.ok, data=message.data, error=message.error, verified=message.verified),
    )
