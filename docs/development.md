# Development

## Prerequisites

- Python 3.12+
- Node.js 20+ and npm
- Docker (for PostgreSQL, or the whole backend)

## Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # then set OPENAI_API_KEY

docker compose up -d postgres # from the repo root: starts only the database
alembic upgrade head          # create tables
uvicorn app.main:app --reload # http://localhost:8000, docs at /docs
```

Without `OPENAI_API_KEY`, everything works except `POST /api/v1/chat`, which returns
`503` with a clear message.

### Tests

```bash
cd backend
pytest
```

Tests use a temporary SQLite database and a fake AI service, so they need neither
PostgreSQL nor an OpenAI key. (Once pgvector columns exist, the database tests will
need to run against PostgreSQL.)

### Migrations

After changing models in `app/database/models/`:

```bash
alembic revision --autogenerate -m "describe the change"
# review the generated file in alembic/versions/, then:
alembic upgrade head
```

New model modules must be imported in `app/database/models/__init__.py`, or Alembic
won't see them. `alembic check` reports whether models and migrations are in sync.

## Web dashboard

```bash
cd web
npm install
npm run dev                   # http://localhost:3000
```

The dashboard calls the backend at `NEXT_PUBLIC_API_URL` (default
`http://localhost:8000`). To change it, copy `web/.env.example` to `web/.env.local`.
If you serve the dashboard from another origin, add it to `CORS_ORIGINS` in
`backend/.env`.

## Docker Compose

```bash
docker compose up --build     # backend on :8000, PostgreSQL on :5432
```

The backend container applies migrations on start and reads `backend/.env` if it
exists. `DATABASE_URL` is set by Compose to point at the `postgres` service.

If ports 8000 or 5432 are already in use:

```bash
BACKEND_PORT=8001 POSTGRES_PORT=5433 docker compose up --build
```

(If you run the backend on the host against that database, also set `DATABASE_URL`
to use port 5433.)

`docker compose down` stops everything; `docker compose down -v` also deletes the
database volume.

## Simulating a device

Until the Mac Agent exists, you can register a fake device from Python
(`websockets` is installed with `uvicorn[standard]`):

```python
import asyncio, json, websockets

async def main():
    async with websockets.connect("ws://localhost:8000/ws/devices") as ws:
        await ws.send(json.dumps({"type": "register",
                                  "device": {"id": "macbook", "name": "MacBook", "type": "mac"}}))
        print(await ws.recv())          # {"type": "registered"}
        await asyncio.sleep(60)         # online for a minute

asyncio.run(main())
```

While it runs, `GET /api/v1/devices` (and the dashboard, after a reload) shows the
device as online; afterwards it shows as offline.

## Adding a tool

1. Subclass `Tool` in `app/tools/` (see `examples.py`) with a `ToolParameters` model.
2. Set `permission`, and `requires_confirmation = True` if it is dangerous.
3. Register it in `create_default_registry()`.
4. It appears in `GET /api/v1/tools` and runs via `POST /api/v1/tools/{name}/execute`.
