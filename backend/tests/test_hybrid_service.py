"""The local model does what it can; the cloud model only steps in when it must."""

import pytest

from app.ai.service import AIServiceError, ChatMessage, Completion, HybridAIService, ToolCall, ToolSpec
from tests.conftest import ScriptedAI

TOOLS = [ToolSpec(name="browser_click", description="", parameters={"type": "object"})]


class FailingAI(ScriptedAI):
    async def complete(self, messages, tools=None):  # type: ignore[override]
        self.calls.append(list(messages))
        raise AIServiceError("connection refused")


def _hybrid(local: ScriptedAI) -> tuple[HybridAIService, ScriptedAI]:
    cloud = ScriptedAI(Completion(text="cloud"))
    return HybridAIService(local=local, cloud=cloud), cloud


@pytest.mark.anyio
async def test_local_model_answers_when_it_can() -> None:
    hybrid, cloud = _hybrid(ScriptedAI(Completion(text="local")))

    completion = await hybrid.complete([ChatMessage(role="user", content="salam")], TOOLS)

    assert completion.text == "local"
    assert cloud.calls == []


@pytest.mark.anyio
async def test_screenshots_go_straight_to_the_cloud() -> None:
    local = ScriptedAI(Completion(text="local"))
    hybrid, _ = _hybrid(local)

    completion = await hybrid.complete([ChatMessage(role="user", content="bax", images=["data:image/jpeg;base64,AA"])])

    assert completion.text == "cloud"
    assert local.calls == []  # the local model cannot see images


@pytest.mark.anyio
@pytest.mark.parametrize(
    "local",
    [
        FailingAI(),
        ScriptedAI(Completion(tool_calls=[ToolCall(id="1", name="browser_tap", arguments={})])),
        ScriptedAI(Completion()),
    ],
    ids=["error", "unknown-tool", "empty"],
)
async def test_cloud_takes_over_steps_the_local_model_gets_wrong(local: ScriptedAI) -> None:
    hybrid, cloud = _hybrid(local)

    completion = await hybrid.complete([ChatMessage(role="user", content="klikle")], TOOLS)

    assert completion.text == "cloud"
    assert len(cloud.calls) == 1
