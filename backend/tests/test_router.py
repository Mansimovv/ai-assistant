import pytest

from app.ai.router import AIRouter
from app.ai.service import ChatMessage, Completion, ToolCall
from app.devices.capabilities import Risk
from app.tools.registry import create_default_registry
from tests.conftest import ScriptedAI


def _messages(text: str = "salam") -> list[ChatMessage]:
    return [ChatMessage(role="system", content="system"), ChatMessage(role="user", content=text)]


@pytest.mark.anyio
async def test_plain_question_needs_no_tools(connected_mac) -> None:
    devices, _ = connected_mac
    ai = ScriptedAI(Completion(text="Yaxşıyam, sən necəsən?"))
    router = AIRouter(ai, create_default_registry(), devices)

    turn = await router.handle(_messages())

    assert turn.text == "Yaxşıyam, sən necəsən?"
    assert turn.actions == []
    assert "mac_open_app" in ai.tools_offered[0]  # the model was told what the Mac can do


@pytest.mark.anyio
async def test_device_tool_runs_and_result_goes_back_to_the_model(connected_mac) -> None:
    devices, socket = connected_mac
    ai = ScriptedAI(
        Completion(tool_calls=[ToolCall(id="c1", name="mac_open_app", arguments={"name": "TextEdit"})]),
        Completion(text="TextEdit-i açdım."),
    )
    router = AIRouter(ai, create_default_registry(), devices)

    turn = await router.handle(_messages("TextEdit aç"))

    assert socket.invocations[0]["capability"] == "open_app"
    assert socket.invocations[0]["arguments"] == {"name": "TextEdit"}
    assert turn.text == "TextEdit-i açdım."
    assert [(a.tool, a.ok) for a in turn.actions] == [("mac_open_app", True)]
    # The second model call saw the real tool result.
    assert ai.calls[1][-1].role == "tool"
    assert '"ok": true' in (ai.calls[1][-1].content or "")


@pytest.mark.anyio
async def test_high_risk_tool_is_not_executed_without_confirmation(connected_mac) -> None:
    devices, socket = connected_mac
    ai = ScriptedAI(
        Completion(tool_calls=[ToolCall(id="c1", name="mac_run_command", arguments={"command": "rm -rf /"})]),
        Completion(text="Bu əmri təsdiqləməlisən."),
    )
    router = AIRouter(ai, create_default_registry(), devices)

    turn = await router.handle(_messages("rm -rf / işlət"))

    assert socket.invocations == []  # nothing reached the device
    assert [(r.tool, r.risk) for r in turn.requested] == [("mac_run_command", Risk.HIGH)]
    assert turn.actions[0].error == "confirmation_required"


@pytest.mark.anyio
async def test_failed_tool_is_reported_not_hidden(connected_mac) -> None:
    devices, _ = connected_mac
    ai = ScriptedAI(
        Completion(tool_calls=[ToolCall(id="c1", name="mac_unknown_thing", arguments={})]),
        Completion(text="Bunu bacarmıram."),
    )
    router = AIRouter(ai, create_default_registry(), devices)

    turn = await router.handle(_messages())

    assert turn.actions[0].ok is False
    assert ai.calls[1][-1].content and '"ok": false' in ai.calls[1][-1].content


@pytest.mark.anyio
async def test_loop_stops_at_the_step_budget(connected_mac) -> None:
    devices, _ = connected_mac
    loops = [
        Completion(tool_calls=[ToolCall(id=f"c{i}", name="mac_open_app", arguments={"name": "TextEdit"})])
        for i in range(3)
    ]
    ai = ScriptedAI(*loops, Completion(text="Dayandım."))
    router = AIRouter(ai, create_default_registry(), devices, max_steps=3)

    turn = await router.handle(_messages())

    assert len(turn.actions) == 3
    assert turn.text == "Dayandım."
    assert ai.tools_offered[-1] == []  # the final call offers no tools, forcing an answer


@pytest.mark.anyio
async def test_full_autonomy_runs_high_risk_tools_without_asking(connected_mac) -> None:
    devices, socket = connected_mac
    router = AIRouter(ScriptedAI(), create_default_registry(), devices, full_autonomy=True)

    payload, record = await router.run_tool("mac_run_in_terminal", {"command": "ssh root@10.0.0.5"}, requested := [])

    assert socket.invocations[0]["capability"] == "run_in_terminal"
    assert requested == []
    assert record.ok


@pytest.mark.anyio
@pytest.mark.parametrize("command", ["rm -rf ~/Projects", "sudo shutdown -h now", "git push -f origin main"])
async def test_full_autonomy_still_holds_back_destructive_commands(connected_mac, command: str) -> None:
    devices, socket = connected_mac
    router = AIRouter(ScriptedAI(), create_default_registry(), devices, full_autonomy=True)

    payload, _ = await router.run_tool("mac_run_command", {"command": command}, requested := [])

    assert socket.invocations == []
    assert payload["error"] == "confirmation_required"
    assert [r.tool for r in requested] == ["mac_run_command"]


@pytest.mark.anyio
async def test_screenshot_is_shown_to_the_model_but_not_stored() -> None:
    """The model must see the screen; the database must not fill up with images."""
    from app.agents.base import AgentConnection
    from app.agents.bus import CommandBus, CommandResult
    from app.agents.manager import AgentManager
    from app.ai.service import _to_openai_message
    from app.devices.actions import DeviceActions
    from tests.conftest import FakeSocket

    agents = AgentManager()
    bus = CommandBus(agents)
    image = "data:image/jpeg;base64,AAAA"
    socket = FakeSocket(
        bus, CommandResult(ok=True, data={"texts": ["Safari"], "screenshot": image}, verified=True)
    )
    agents.connect(AgentConnection("mac", "MacBook", "mac", ["look_at_screen"], socket, []))  # type: ignore[arg-type]
    ai = ScriptedAI(
        Completion(tool_calls=[ToolCall(id="c1", name="mac_look_at_screen", arguments={})]),
        Completion(tool_calls=[ToolCall(id="c2", name="mac_look_at_screen", arguments={})]),
        Completion(text="Ekranda Safari açıqdır."),
    )
    router = AIRouter(ai, create_default_registry(), DeviceActions(agents, bus))

    turn = await router.handle(_messages("ekrana bax"))

    seen = ai.calls[-1]
    assert [m.images for m in seen if m.images] == [[image]]  # only the latest screenshot
    assert _to_openai_message(seen[-1])["content"][1]["image_url"]["url"] == image
    # Only the latest screen reading is resent in full; the older one is shortened.
    screen_readings = [m.content or "" for m in seen if m.role == "tool"]
    assert ["Safari" in content for content in screen_readings] == [False, True]
    # The stored turn keeps both readings intact.
    assert sum("Safari" in (m.content or "") for m in turn.messages if m.role == "tool") == 2
    assert all(not m.images and image not in (m.content or "") for m in turn.messages)
    assert turn.text == "Ekranda Safari açıqdır."


@pytest.mark.anyio
async def test_turn_logs_the_tokens_of_every_step(connected_mac, caplog) -> None:
    devices, _ = connected_mac
    ai = ScriptedAI(
        Completion(
            tool_calls=[ToolCall(id="c1", name="mac_open_app", arguments={"name": "TextEdit"})],
            input_tokens=1000,
            cached_tokens=800,
            output_tokens=20,
        ),
        Completion(text="Açdım.", input_tokens=1100, cached_tokens=1000, output_tokens=10),
    )
    router = AIRouter(ai, create_default_registry(), devices)

    with caplog.at_level("INFO", logger="app.ai.router"):
        await router.handle(_messages("TextEdit aç"))

    assert "turn steps=2 tokens in=2100 (cached=1800) out=30" in caplog.text
