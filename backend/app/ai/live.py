"""Voice sessions with GPT-Live (OpenAI Live API).

GPT-Live is the voice: it listens and speaks at the same time, handles interruptions
and pauses, and answers small talk itself. Anything that needs real work it
*delegates* (client delegation): the browser receives `session.delegation.created`,
sends what the user said to the same brain the text chat uses (tools, screen, memory,
confirmations), and hands the result back with `session.commentary.append`, which the
voice then says.

The browser's WebRTC offer is answered here, with the real API key, so the key never
reaches the browser.
"""

import logging

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel

from app.ai.service import AIServiceError, AIServiceNotConfiguredError, ChatMessage

logger = logging.getLogger(__name__)

# Live accepts at most 128 history messages and 8,192 tokens of history.
HISTORY_MESSAGES = 30
HISTORY_MESSAGE_CHARS = 600

LIVE_INSTRUCTIONS = """You are {app_name}, the voice of {owner}'s personal assistant - like Jarvis
for Tony Stark. You talk; a backend assistant does the work.

How you speak:
- Natural, flawless Azerbaijani as spoken in Baku: warm, calm, short sentences, the way a
  capable human assistant talks on a call. Address {owner} by name now and then.
- It is Azerbaijani, not Turkish: "indi" not "şimdi", "bəli" not "evet", "xeyr" not
  "hayır", "çox" not "çok", "yaxşı/oldu" not "tamam", "edirəm" not "yapıyorum".
- Say numbers, times and dates as words. Never read out code, JSON or file paths.

When to delegate:
- The backend assistant has full access to {owner}'s Mac (apps, files, terminal, the
  screen, mouse and keyboard, the web, Claude Code for software projects) and remembers
  everything {owner} has told it. You do not.
- Delegate right away, without asking first, whenever the request needs any action,
  checking something, current information, the screen, a file, a project, or anything
  {owner} said before. Say a very short "bir saniyə" while it works.
- When the result arrives, say it in one or two natural sentences. Never claim something
  happened unless the result says so. If it says confirmation is needed, ask {owner} to
  confirm (by voice or on screen) and delegate their answer.
- Small talk and simple questions you can answer yourself.

What you know about {owner}:
{memory}"""


class LiveSession(BaseModel):
    session_id: str
    sdp: str


class LiveService:
    def __init__(self, api_key: str | None, model: str, voice: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None
        self._model = model
        self._voice = voice

    async def connect(
        self,
        offer_sdp: str,
        app_name: str,
        owner: str,
        memory: str,
        history: list[ChatMessage],
    ) -> LiveSession:
        """Start a Live session for the browser's WebRTC offer and return the answer."""
        if self._client is None:
            raise AIServiceNotConfiguredError("OPENAI_API_KEY is not set")

        instructions = LIVE_INSTRUCTIONS.format(app_name=app_name, owner=owner, memory=memory or "Nothing yet.")
        try:
            created = await self._client.live.create(
                session={
                    "model": self._model,
                    "instructions": instructions,
                    "audio": {"output": {"voice": self._voice}},
                    "delegation": {"type": "client"},
                    "input": _history_items(history),
                },
                transport={"type": "webrtc", "sdp": offer_sdp},
            )
        except OpenAIError as exc:
            logger.exception("Could not create a Live session")
            raise AIServiceError("Could not start a voice session") from exc

        logger.info("Live session %s started (model=%s, history=%d)", created.session.id, self._model, len(history))
        return LiveSession(session_id=created.session.id, sdp=created.transport.sdp)


def _history_items(history: list[ChatMessage]) -> list[dict[str, object]]:
    """The recent conversation as Live's text-only startup history."""
    items: list[dict[str, object]] = []
    for message in history:
        if message.role not in ("user", "assistant") or not message.content:
            continue
        text = message.content[:HISTORY_MESSAGE_CHARS]
        part_type = "input_text" if message.role == "user" else "output_text"
        items.append({"type": "message", "role": message.role, "content": [{"type": part_type, "text": text}]})
    return items[-HISTORY_MESSAGES:]
