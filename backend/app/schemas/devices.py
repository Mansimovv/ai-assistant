from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.devices.base import DeviceStatus, DeviceType


class DeviceRead(BaseModel):
    id: str
    name: str
    type: DeviceType
    status: DeviceStatus
    last_seen: datetime | None
    capabilities: list[str] = Field(default_factory=list)


class DeviceRegistration(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    type: DeviceType


class RegisterMessage(BaseModel):
    """First message a device agent sends on /ws/devices."""

    type: Literal["register"]
    device: DeviceRegistration
    capabilities: list[str] = Field(default_factory=list)
    token: str | None = None


class ResultMessage(BaseModel):
    """An agent's answer to an invoke."""

    type: Literal["result"]
    call_id: str
    ok: bool
    data: Any = None
    error: str | None = None
    verified: bool = False
