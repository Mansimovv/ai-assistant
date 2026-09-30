# Development

Everything runs on this machine.

**Just want to use it?** `docker compose up --build -d`, then start the Mac agent
(`cd agents/mac && ./install-autostart.sh`) and open <http://localhost:3000>.

The rest of this page is for working *on* it, where running the backend and web outside
Docker gives you reload-on-save.

## Prerequisites

- Python 3.12+, Node.js 20+, Docker
- An OpenAI API key (without it, chat returns `503` with a clear message)

## 1. Database

```bash
docker compose up -d postgres
```

Host ports come from the repository `.env` (`POSTGRES_PORT`, `BACKEND_PORT`) so they can
be moved when another project already uses 5432/8000.

## 2. Backend

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # set OPENAI_API_KEY, check DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload # http://localhost:8000, API docs at /docs
```

## 3. Web

```bash
cd web
npm install
npm run dev                   # http://localhost:3000
```

It calls the backend at `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). To point
it elsewhere, copy `web/.env.example` to `web/.env.local`.

## 4. Mac agent

```bash
cd agents/mac
./install-autostart.sh          # runs now and at every login (LaunchAgent)
# or by hand:
python3 agent.py --server ws://localhost:8001/ws/devices
```

The agent must run on the Mac itself — a container cannot open apps or run `osascript`.
It shows up in the dashboard as online with its capabilities. Remove the LaunchAgent with
`./uninstall-autostart.sh`. See [agents/mac/README.md](../agents/mac/README.md).

## 5. Voice

The microphone button in the dashboard opens an OpenAI Realtime session:

1. The browser asks the backend for a short-lived credential (`POST /api/v1/voice/session`),
   which also configures the session with the current device list and the same tools the
   text path uses. The real API key never reaches the browser.
2. Audio goes browser ↔ OpenAI directly over WebRTC, which is what keeps latency low.
3. Tool calls come back to the backend (`POST /api/v1/voice/tool`), so risk gating,
   confirmation and the audit log apply exactly as in text.
4. Transcripts are stored (`POST /api/v1/voice/turn`), so voice and text share one thread.

Settings: `REALTIME_MODEL`, `REALTIME_VOICE`, `VOICE_LANGUAGE`, `REALTIME_TRANSCRIBE_MODEL`.

Audio is billed per minute, so the session closes itself after two minutes of silence.
Keep a spend limit set in the OpenAI dashboard.

## Renaming the assistant

Set `APP_NAME` in `backend/.env`. The API reports it and the web client reads it from
there, so that one variable renames everything.

## Tests

```bash
cd backend
pytest
```

They use a temporary SQLite database, a scripted fake model and a fake agent socket, so
they need neither PostgreSQL, nor an API key, nor a real device. What is covered:

- the agent loop (tool call → real result → answer)
- high-risk actions are **not** executed without confirmation, and only once
- failures and timeouts are reported, never turned into success
- conversation history and the audit log
- device registration, capability filtering, and the dispatcher

## Migrations

After changing models in `app/database/models/`:

```bash
alembic revision --autogenerate -m "describe the change"
# review the generated file, then
alembic upgrade head
```

New model modules must be imported in `app/database/models/__init__.py`. `alembic check`
tells you whether models and migrations still match.

## Testing a device without the model

```bash
curl -s localhost:8000/api/v1/tools | jq '.[] | select(.target=="device") | .name'
curl -s -X POST localhost:8000/api/v1/tools/mac_app_status/execute \
  -H 'Content-Type: application/json' -d '{"arguments":{"name":"Safari"}}'
```

Direct executions are audited too, so they appear in `GET /api/v1/activity`.

## Adding a capability

1. Add it to `CAPABILITIES` in `backend/app/devices/capabilities.py` (description,
   parameter model, risk).
2. Implement a handler with the same name in `agents/mac/agent.py` and add it to
   `HANDLERS`.
3. Restart both. The agent announces it, the brain offers it to the model.

Descriptions matter: they are what the model reads to decide when to use the capability.

## Adding a backend-side tool

Subclass `Tool` in `backend/app/tools/` and register it in `create_default_registry()`.
Use this for things that do not belong to a device (time, later: web search, GitHub).

## Docker Compose

```bash
docker compose up --build     # backend + postgres
```

The backend container applies migrations on start and reads `backend/.env` if present.
The web app and the Mac agent run outside Docker.
