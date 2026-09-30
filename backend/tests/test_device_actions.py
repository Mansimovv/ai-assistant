import pytest

from app.agents.base import AgentConnection
from app.agents.bus import CommandBus, CommandResult, DeviceOfflineError
from app.agents.manager import AgentManager
from app.devices.actions import DeviceActions
from app.devices.capabilities import Risk


def test_only_online_capabilities_become_tools(connected_mac) -> None:
    devices, _ = connected_mac

    names = {spec.name for spec in devices.specs()}

    assert names == {"mac_open_app", "mac_docker_status", "mac_run_command", "mac_run_in_terminal"}
    assert devices.risk("mac_run_command") is Risk.HIGH
    # Opening a visible Terminal can do anything a shell can, so it is gated too.
    assert devices.risk("mac_run_in_terminal") is Risk.HIGH
    assert devices.risk("mac_open_app") is Risk.LOW
    assert devices.knows("mac_open_app")
    assert not devices.knows("mac_close_app")  # not announced by this agent


@pytest.mark.anyio
async def test_invalid_arguments_never_reach_the_device(connected_mac) -> None:
    devices, socket = connected_mac

    result = await devices.execute("mac_open_app", {"wrong": "arg"})

    assert result.ok is False
    assert "Invalid arguments" in (result.error or "")
    assert socket.invocations == []


@pytest.mark.anyio
async def test_unknown_tool_is_reported(connected_mac) -> None:
    devices, _ = connected_mac

    result = await devices.execute("mac_take_over_the_world", {})

    assert result.ok is False
    assert "No online device" in (result.error or "")


@pytest.mark.anyio
async def test_offline_device_raises() -> None:
    bus = CommandBus(AgentManager())

    with pytest.raises(DeviceOfflineError):
        await bus.invoke("mac", "open_app", {"name": "TextEdit"})


@pytest.mark.anyio
async def test_silent_device_times_out_instead_of_claiming_success() -> None:
    agents = AgentManager()
    bus = CommandBus(agents)
    agents.connect(AgentConnection("mac", "MacBook", "mac", ["docker_status"], _SilentSocket()))  # type: ignore[arg-type]
    devices = DeviceActions(agents, bus, timeout=0.2)

    result = await devices.execute("mac_docker_status", {})

    assert result.ok is False
    assert "did not answer" in (result.error or "")


class _SilentSocket:
    async def send_json(self, message: dict) -> None:
        return None


@pytest.mark.anyio
async def test_result_is_passed_through(connected_mac) -> None:
    devices, _ = connected_mac

    result = await devices.execute("mac_open_app", {"name": "TextEdit"})

    assert result == CommandResult(ok=True, data={"running": True}, verified=True)
