# Architecture

One brain, many devices. The backend holds all reasoning, memory and policy; devices
run small agents that execute actions and report real results.

```text
   Web client (browser)              Mac agent (agents/mac/agent.py)
          │  HTTP                              │  WebSocket (outbound only)
          └───────────────► BRAIN (FastAPI) ◄───┘
                                │
                     PostgreSQL (conversations, audit, memory)
```

Everything runs locally for now: backend on `localhost:8000`, web on `localhost:3000`,
Postgres in Docker. Moving the brain to a server later changes URLs and authentication,
not the architecture.

## What happens on one message

```text
"Mac-da VS Code-u aç"
  │
  ▼
POST /api/v1/chat ── Assistant ── loads the shared conversation + device list
                        │
                        ▼
                    AIRouter (agent loop)
                        │  model sees: history + online devices + their capabilities as tools
                        ▼
                    tool call: mac_open_app {"name": "Visual Studio Code"}
                        │
                        ▼
                    DeviceActions → CommandBus → WebSocket → Mac agent
                        │                                       │ open -a, then verify
                        ▼                                       ▼
                    {"ok": true, "verified": true} ◄────────────┘
                        │
                        ▼
                    model gets the real result → final answer → saved + audited
```

The model never reports success on its own: the only thing it can tell the user is what
a tool result says. A timeout or a missing device is a failure, not a success.

## Backend modules (`backend/app/`)

| Module | Responsibility |
| --- | --- |
| `ai/service.py` | `AIService` interface + `OpenAIService`. Nothing else touches a provider SDK. |
| `ai/router.py` | The agent loop: model → tool calls → results → model. Holds back high-risk calls. |
| `ai/assistant.py` | One turn end to end: conversation, system prompt, loop, persistence, confirmations. |
| `ai/confirmations.py` | High-risk actions parked until the user confirms (in memory, on purpose). |
| `ai/prompts.py` | The system prompt, including the live device list. |
| `ai/planner.py` | `Plan`/`PlanStep` types for future explicit planning (not used yet). |
| `agents/manager.py` | Which agents are connected right now (in memory). |
| `agents/bus.py` | `CommandBus`: invoke a capability, wait for the matching `call_id`, time out honestly. |
| `devices/capabilities.py` | The capability catalog: descriptions, argument schemas, risk. |
| `devices/actions.py` | Turns online capabilities into model tools and dispatches them. |
| `devices/manager.py` | Registered devices, live status, and the device summary for the prompt. |
| `memory/conversations.py` | The rolling conversation, message history, audit log. |
| `memory/service.py` | Long-term memory (facts, preferences). Not wired into chat yet. |
| `api/` | Routes, WebSocket endpoint, dependency wiring. |
| `core/` | Settings, logging, security primitives. |
| `database/` | Async SQLAlchemy engine/session and ORM models. |

## Capabilities and tool names

The catalog lives on the brain so there is one source of truth for schemas and risk. An
agent announces the capability *names* it implements; the brain exposes them to the
model as `<device type>_<capability>` (e.g. `mac_open_app`) and validates arguments
before anything is sent to a device.

Consequences:

- Only **online** devices contribute tools, so the model cannot call something that has
  no chance of running.
- An unknown capability announced by an agent is ignored, not trusted.
- The device is implied by the tool name, so the user never says "target device = Mac".
  If several devices of the same type are online, the tool returns an error telling the
  model to ask which one.

## Risk and confirmation

| Risk | Examples | Behaviour |
| --- | --- | --- |
| low | `app_status`, `docker_status`, `open_app`, `list_apps`, `find_files` | runs immediately |
| medium | `close_app` | runs immediately |
| high | `run_command`, `run_in_terminal` | **never** runs on the model's word alone |

A high-risk call is parked as a pending action. The model is told to show the user
exactly what it would do; the client renders a confirm/cancel card; only
`POST /api/v1/actions/{id}/confirm` executes it. Pending actions are single-use, expire
after 10 minutes, and are lost on restart by design.

## Voice

```text
browser mic ──WebRTC──► OpenAI Realtime ──tool call──► browser ──HTTP──► BRAIN ──► Mac agent
     ▲                        │                                                      │
     └──────── speech ────────┘◄──────────────── real result ◄─────────────────────--┘
```

- `POST /api/v1/voice/session` mints a short-lived client secret and configures the
  session with the current device list and the same tool specs the text loop uses. The
  real API key never reaches the browser.
- Audio flows browser ↔ OpenAI directly, which is what keeps latency low. The brain is
  not in the audio path.
- Tool calls are *not* executed by the browser: they are posted to
  `POST /api/v1/voice/tool`, which runs them through `AIRouter.run_tool` — the same risk
  gating, confirmation and audit as text. A high-risk call returns
  `confirmation_required` plus a pending action, and the user confirms on screen.
- Transcripts are stored via `POST /api/v1/voice/turn`, so spoken and typed turns live in
  one conversation.
- Cost: audio is billed per minute, so the browser closes an idle session after two
  minutes, and the cheap realtime model is the default.

A session's tool list is a snapshot from when it was created; a device that connects
mid-session is not offered until the next session.

## Understanding informal Azerbaijani

Most "it did not understand me" problems were not the model's size but missing context,
so they are fixed in three places rather than by paying for a bigger model:

- **The system prompt** (`ai/prompts.py`) states that the user writes spoken Azerbaijani
  without diacritics, maps common phrasings to intents ("gir" → connect, "ac gorum" → open
  and show), forbids answering in English, and requires asking for a repeat instead of
  guessing from a garbled voice transcript.
- **The agent** resolves application names against what is installed, stripping
  Azerbaijani suffixes ("termiusu" → "Termius"), so a spelling difference cannot fail a
  request.
- **Voice transcription** is given the device's real application names as a hint, which is
  what stops "Termius" from arriving as "Termini".

## Conversation model

One rolling conversation: any client joins the same thread, so a talk started on one
device continues on another. After 60 minutes of silence the next message starts a new
conversation. History is stored as real message roles (`user`, `assistant`, `tool`,
`system`), which is exactly what the model is fed again on the next turn.

## Audit

Every executed tool call is written to `tool_calls`: what ran, with which arguments,
whether it worked, the error, and how long it took. This is the answer to "what did it
actually do?" and it is what the dashboard's activity list shows.

## Security (current state)

- Provider API keys live only in backend environment variables; the browser never sees them.
- Docker Compose publishes ports on `127.0.0.1` only; the Mac agent connects outbound.
- `AGENT_TOKEN`, when set, is required from device agents.
- `get_current_user` (`core/security.py`) is the authentication hook. It currently returns
  the local owner: **single-user, local-machine mode**.
- `run_command` is a shell on the Mac. It is gated by confirmation, but treat the whole
  system as trusted-local until real authentication exists.

**Before the brain leaves this machine:** real authentication in `get_current_user`,
per-device credentials instead of one shared token, and a stricter policy for
`run_command` (allowlist or disabled remotely).

## Known limits

- Agent connections and pending actions live in memory → one backend process only.
- Long-term memory (`memory/service.py`) is not used by the chat flow yet.
- No voice yet; text only.
- Tests use SQLite; when pgvector arrives they move to PostgreSQL.
