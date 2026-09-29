# Personal AI

A personal AI agent that understands natural language and, over time, acts on your
devices, applications, files, browser, APIs and services.

> **Status:** early foundation. Chat, the tool registry, device registration and the
> dashboard work; the assistant cannot act on devices yet.

## Vision

One assistant you can ask things like:

- "Open VS Code on my Mac."
- "Check my GitHub PRs."
- "Open the project I worked on yesterday."
- "Take a screenshot of my Mac."
- "Run the tests for this project."
- "Check my calendar."
- "Do this on my iPhone."

It spans Mac, iPhone, Linux/Windows machines, browsers and servers, with a central
backend as the brain and small agents on each device carrying out actions, all
behind a permission system with confirmation for dangerous actions.

## Architecture

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

- **Backend (FastAPI):** a single application. All model calls, tools and device
  communication go through it.
- **AI core:** `AIService` hides the model provider; `AIRouter` is the entry point
  for every message; `Planner` will turn requests into tool calls.
- **Tools:** each capability is a `Tool` with a validated parameter schema, a
  permission level and an optional confirmation requirement.
- **Devices:** agents connect over WebSocket (`/ws/devices`) and appear as online
  while connected.

Details: [docs/architecture.md](docs/architecture.md).

## Technology stack

| Area | Stack |
| --- | --- |
| Backend | Python 3.12+, FastAPI, Pydantic, Uvicorn, WebSockets |
| Database | PostgreSQL 17, SQLAlchemy 2 (async, psycopg 3), Alembic |
| AI | OpenAI API (Responses API) behind an `AIService` abstraction |
| Web | Next.js 16 (App Router), TypeScript, Tailwind CSS 4 |
| Infra | Docker Compose |

## Project structure

```text
.
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, routers, CORS
│   │   ├── api/
│   │   │   ├── routes/          # health, chat, devices, tools
│   │   │   ├── websocket.py     # /ws/devices
│   │   │   └── deps.py          # dependency wiring
│   │   ├── core/                # config, security, logging
│   │   ├── ai/                  # service, router, planner, prompts
│   │   ├── agents/              # server side of device-agent connections
│   │   ├── tools/               # Tool base, registry, example tools
│   │   ├── devices/             # device types, DeviceManager
│   │   ├── memory/              # MemoryService
│   │   ├── database/            # engine/session, ORM models
│   │   └── schemas/             # API request/response models
│   ├── alembic/                 # migrations
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── .env.example
├── web/                         # Next.js dashboard (app/, components/, lib/)
├── agents/
│   └── mac/                     # future Mac Agent (placeholder)
├── docs/
│   ├── architecture.md
│   └── development.md
├── docker-compose.yml
└── README.md
```

## Local development

Prerequisites: Python 3.12+, Node.js 20+, Docker.

```bash
git clone <repo> && cd ai-assistant
docker compose up -d postgres     # database only
```

Then run the backend and the frontend as below. More detail, including tests and
migrations, is in [docs/development.md](docs/development.md).

## Environment variables

Backend (`backend/.env`, copied from `backend/.env.example`; never commit `.env`):

| Variable | Description |
| --- | --- |
| `APP_ENV` | `development` (default) or `production`. Production requires `SECRET_KEY`. |
| `OPENAI_API_KEY` | OpenAI API key. Without it, chat returns `503`. |
| `OPENAI_MODEL` | Model name. Defaults to `gpt-5.4-mini` when empty. |
| `DATABASE_URL` | SQLAlchemy URL, e.g. `postgresql+psycopg://postgres:postgres@localhost:5432/personal_ai` |
| `SECRET_KEY` | Secret for future token signing. |
| `CORS_ORIGINS` | JSON list of browser origins allowed to call the API. Default `["http://localhost:3000"]`. |

Web (`web/.env.local`, optional): `NEXT_PUBLIC_API_URL` — backend URL, default
`http://localhost:8000`. It is public by design; never put secrets in `NEXT_PUBLIC_*`.

## Running the backend

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # set OPENAI_API_KEY
alembic upgrade head
uvicorn app.main:app --reload     # http://localhost:8000 (API docs at /docs)
pytest                            # run the tests
```

### Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/` | API information |
| GET | `/health` | `{"status": "ok"}` |
| POST | `/api/v1/chat` | `{"message": "Hello"}` → `{"message": "..."}` |
| GET | `/api/v1/devices` | Registered devices with live status |
| GET | `/api/v1/tools` | Available tools and their parameter schemas |
| POST | `/api/v1/tools/{name}/execute` | `{"arguments": {...}, "confirmed": false}` |
| WS | `/ws/devices` | Device agent channel |

## Running the frontend

```bash
cd web
npm install
npm run dev                       # http://localhost:3000
```

## Docker

```bash
cp backend/.env.example backend/.env   # optional; set OPENAI_API_KEY
docker compose up --build              # backend :8000 + PostgreSQL :5432
```

The backend container runs migrations on start. Ports are bound to `127.0.0.1`. If
8000 or 5432 are taken: `BACKEND_PORT=8001 POSTGRES_PORT=5433 docker compose up --build`.

## Roadmap

```text
[x] Initial project structure
[x] FastAPI backend
[x] Basic chat API
[x] AI service abstraction
[x] Tool registry
[x] Device abstraction
[x] Basic web dashboard

[ ] OpenAI function calling
[ ] Real tool execution
[ ] Mac Agent
[ ] Mac terminal control
[ ] Mac application control
[ ] Browser Agent
[ ] GitHub integration
[ ] Memory
[ ] Voice input
[ ] iPhone application
[ ] Multi-device communication
[ ] Permission system
[ ] Autonomous tasks
[ ] Proactive assistant
```

## License

[MIT](LICENSE)
