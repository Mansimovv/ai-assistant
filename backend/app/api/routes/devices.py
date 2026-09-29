from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_device_manager
from app.devices.manager import DeviceManager
from app.schemas.devices import DeviceRead

router = APIRouter(tags=["devices"])


@router.get("/devices")
async def list_devices(devices: Annotated[DeviceManager, Depends(get_device_manager)]) -> list[DeviceRead]:
    return await devices.list_devices()
