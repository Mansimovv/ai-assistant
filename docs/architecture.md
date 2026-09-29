# Architecture

Personal AI is one FastAPI application (the "brain"), a PostgreSQL database, a web
dashboard, and — later — small agents running on each device.

```text
                    PERSONAL AI
                         |
                  ┌──────▼──────┐
                  │  AI Backend │
                  │   FastAPI   │
                  └──────┬──────┘
                         |
          ┌──────────────┼──────────────┐
          |              |              |
       AI Core         Tools         Devices
          |              |              |
       OpenAI         Tool Registry   Device Agents
          |              |              |
       Memory         Browser         Mac Agent
       Planner        Files           iPhone
       Router         Terminal       Future devices
```

## Backend modules (`backend/app/`)

| Module | Responsibility |
| --- | --- |
| `api/routes/` | HTTP endpoints. Thin: validate input, call a service, map errors to status codes. |
| `api/websocket.py` | `/ws/devices`, the real-time channel device agents connect to. |
| `api/deps.py` | Dependency providers: the one place implementations are wired together (and swapped in tests). |
| `core/` | Settings (`config.py`), logging, security primitives (`security.py`). |
| `ai/service.py` | `AIService` interface + `OpenAIService`. Nothing else imports the OpenAI SDK. |
| `ai/router.py` | `AIRouter`, the entry point for every user message. |
| `ai/planner.py` | `Plan` / `PlanStep` models and the `Planner` interface (not wired in yet). |
| `ai/prompts.py` | System prompts. |
| `tools/` | `Tool` contract, `ToolRegistry`, example tools. |
| `devices/` | Device types/statuses and `DeviceManager` (registered devices + live status). |
| `agents/` | Server side of device agents: `AgentConnection` wraps a socket, `AgentManager` tracks who is connected. |
| `memory/` | `MemoryService` for long-term memory. |
| `database/` | Async SQLAlchemy engine/session and ORM models. |
| `schemas/` | Pydantic request/response models for the API. |

`backend/app/agents/` is the server's view of device agents. The agents themselves
will live in the top-level `agents/` folder (e.g. `agents/mac/`).

## Request flow

Today:

```text
POST /api/v1/chat → AIRouter.handle → AIService.complete → OpenAI → response
```

Target, once function calling lands:

```text
User → Chat API → AIRouter → Planner → tool selection → ToolRegistry.execute → response
```

The seams already exist: the route only knows `AIRouter`, `AIRouter` only knows the
`AIService` interface, and tools only run through `ToolRegistry.execute`, which
validates arguments and enforces confirmation.

## Changing the model or provider

- **Model:** set `OPENAI_MODEL`. No code change.
- **Provider:** implement `AIService.complete` in a new class and return it from
  `get_ai_service()` in `app/api/deps.py`. Routes and `AIRouter` stay the same.

## Tools

A tool subclasses `Tool` and declares:

- `name`, `description` — what the model sees
- `parameters` — a Pydantic model, exported as JSON Schema for function calling and
  used to validate arguments (unknown arguments are rejected)
- `permission` — the `Permission` level it needs
- `requires_confirmation` — set on dangerous tools; the registry refuses to run them
  unless `confirmed=True`
- `async execute(params)` — returns a JSON-serializable result

Register new tools in `create_default_registry()` (`app/tools/registry.py`).

## Devices

- Devices are stored in the `devices` table (`id`, `name`, `type`, `last_seen`).
- **Status is derived, not stored:** a device is `online` exactly while its agent
  holds a WebSocket open (`AgentManager`), so it can't go stale after a crash.
- Agents register with `{"type": "register", "device": {...}}` as their first
  message (see `agents/mac/README.md`).
- `AgentManager` keeps connections in memory, which works for one backend process.
  Several workers would need a shared channel such as Redis pub/sub.

## Memory

`MemoryService` stores `Memory` rows tagged with a `MemoryKind` (conversation,
preference, project, device, task, context). `search()` is plain text matching for
now; with pgvector it becomes similarity search over an `embedding` column without
changing callers.

## Database

Tables: `devices`, `conversations`, `messages`, `memories`, managed by Alembic
(`backend/alembic/`). The app uses async SQLAlchemy and Alembic a sync engine; both
read the same `DATABASE_URL` through psycopg 3, which supports both modes.

## Security

- API keys live only in backend environment variables; the web app never sees them.
- Docker Compose publishes ports on `127.0.0.1` only.
- `get_current_user` (`app/core/security.py`) is the authentication hook; every
  `/api/v1` route depends on it. Today it returns the local owner (single-user local
  mode). Real authentication (tokens signed with `SECRET_KEY`) goes there.
- Permission levels: `READ`, `WRITE`, `EXECUTE`, `MESSAGE`, `SYSTEM`, `ADMIN`. Tools
  declare one; enforcing them per user is future work.
- Dangerous tools require explicit confirmation, enforced in `ToolRegistry`.
- `APP_ENV=production` refuses to start without `SECRET_KEY`.

**Before exposing the backend beyond localhost:** implement real authentication in
`get_current_user`, authenticate device agents on `/ws/devices`, and restrict CORS.
