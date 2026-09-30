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
