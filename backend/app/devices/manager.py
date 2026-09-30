from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.manager import AgentManager
from app.database.models import Device
from app.devices.base import DeviceStatus
from app.schemas.devices import DeviceRead, DeviceRegistration


class DeviceManager:
    """Registered devices (stored in the database) and their live status.

    Status is not stored: a device is online exactly while its agent is connected.
    """

    def __init__(self, session: AsyncSession, agents: AgentManager) -> None:
        self._session = session
        self._agents = agents

    async def list_devices(self) -> list[DeviceRead]:
        devices = await self._session.scalars(select(Device).order_by(Device.name))
        return [self._to_schema(device) for device in devices]

    async def register(self, registration: DeviceRegistration) -> None:
        """Create or update a device when its agent connects."""
        device = await self._session.get(Device, registration.id)
        if device is None:
            device = Device(id=registration.id)
            self._session.add(device)
        device.name = registration.name
        device.type = registration.type
        device.last_seen = datetime.now(UTC)
        await self._session.commit()

    async def mark_seen(self, device_id: str) -> None:
        await self._session.execute(
            update(Device).where(Device.id == device_id).values(last_seen=datetime.now(UTC))
        )
        await self._session.commit()

    async def summary(self) -> str:
        """Device list for the system prompt, so the model knows what exists right now."""
        lines = []
        for device in await self.list_devices():
            if device.status is DeviceStatus.ONLINE:
                can = ", ".join(device.capabilities) or "nothing yet"
                lines.append(f"- {device.name} (type={device.type}, id={device.id}) - online; can: {can}")
            else:
                lines.append(f"- {device.name} (type={device.type}, id={device.id}) - offline")
        return "\n".join(lines)

    def _to_schema(self, device: Device) -> DeviceRead:
        connection = self._agents.get(device.id)
        return DeviceRead(
            id=device.id,
            name=device.name,
            type=device.type,
            status=DeviceStatus.ONLINE if connection else DeviceStatus.OFFLINE,
            last_seen=device.last_seen,
            capabilities=connection.capabilities if connection else [],
        )
