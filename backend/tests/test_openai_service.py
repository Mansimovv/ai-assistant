"""Checks the real OpenAI SDK request/response wiring without calling OpenAI.

A mock transport captures what the SDK actually puts on the wire and returns a
realistic tool-calling response, so the message conversion and parsing are
verified end to end.
"""

import json
from typing import Any

import httpx
import pytest

from app.ai.service import ChatMessage, OpenAIService, ToolCall, ToolSpec


def _service(handler) -> OpenAIService:
    service = OpenAIService(api_key="test-key", model="gpt-test")
    service._client = service._client.with_options(  # type: ignore[union-attr]
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    return service


def _reply(body: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=body)


TOOL_CALL_RESPONSE = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-test",
    "choices": [
        {
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "mac_open_app", "arguments": '{"name": "TextEdit"}'},
                    }
                ],
            },
        }
    ],
}

TEXT_RESPONSE = {
    "id": "chatcmpl-2",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-test",
    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Açdım."}}],
}


@pytest.mark.anyio
async def test_request_shape_and_tool_call_parsing() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.url.path.endswith("/chat/completions")
        return _reply(TOOL_CALL_RESPONSE)

    service = _service(handler)
    completion = await service.complete(
        [
            ChatMessage(role="system", content="rules"),
            ChatMessage(role="user", content="TextEdit aç"),
        ],
        [ToolSpec(name="mac_open_app", description="Open an app", parameters={"type": "object", "properties": {}})],
    )

    assert captured["model"] == "gpt-test"
    assert captured["messages"] == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "TextEdit aç"},
    ]
    assert captured["tools"][0]["type"] == "function"
    assert captured["tools"][0]["function"]["name"] == "mac_open_app"
    assert completion.text is None
    assert completion.tool_calls == [ToolCall(id="call_1", name="mac_open_app", arguments={"name": "TextEdit"})]


@pytest.mark.anyio
async def test_assistant_tool_calls_and_results_are_sent_back_correctly() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return _reply(TEXT_RESPONSE)

    service = _service(handler)
    completion = await service.complete(
        [
            ChatMessage(role="user", content="TextEdit aç"),
            ChatMessage(
                role="assistant",
                tool_calls=[ToolCall(id="call_1", name="mac_open_app", arguments={"name": "TextEdit"})],
            ),
            ChatMessage(role="tool", tool_call_id="call_1", content='{"ok": true}'),
        ]
    )

    assistant, result = captured["messages"][1], captured["messages"][2]
    assert assistant["tool_calls"] == [
        {"id": "call_1", "type": "function", "function": {"name": "mac_open_app", "arguments": '{"name": "TextEdit"}'}}
    ]
    assert result == {"role": "tool", "tool_call_id": "call_1", "content": '{"ok": true}'}
    assert "tools" not in captured  # no tools offered means no tools field
    assert completion.text == "Açdım."


@pytest.mark.anyio
async def test_invalid_json_arguments_do_not_crash_the_turn() -> None:
    broken = {
        **TOOL_CALL_RESPONSE,
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "call_1", "type": "function", "function": {"name": "mac_open_app", "arguments": "{oops"}}
                    ],
                },
            }
        ],
    }
    service = _service(lambda request: _reply(broken))

    completion = await service.complete([ChatMessage(role="user", content="aç")])

    # Empty arguments fail validation later, and that error goes back to the model.
    assert completion.tool_calls == [ToolCall(id="call_1", name="mac_open_app", arguments={})]


@pytest.mark.anyio
async def test_schema_titles_are_dropped_but_a_field_named_title_stays() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return _reply(TEXT_RESPONSE)

    schema = {
        "title": "NoteParameters",
        "type": "object",
        "properties": {"title": {"title": "Title", "type": "string"}},
    }
    await _service(handler).complete(
        [ChatMessage(role="user", content="qeyd yaz")], [ToolSpec(name="note", description="", parameters=schema)]
    )

    assert captured["tools"][0]["function"]["parameters"] == {
        "type": "object",
        "properties": {"title": {"type": "string"}},
    }


@pytest.mark.anyio
async def test_token_usage_is_returned_with_the_completion() -> None:
    body = {
        **TEXT_RESPONSE,
        "usage": {
            "prompt_tokens": 1200,
            "completion_tokens": 15,
            "total_tokens": 1215,
            "prompt_tokens_details": {"cached_tokens": 1024},
        },
    }

    completion = await _service(lambda request: _reply(body)).complete([ChatMessage(role="user", content="salam")])

    assert (completion.input_tokens, completion.cached_tokens, completion.output_tokens) == (1200, 1024, 15)
