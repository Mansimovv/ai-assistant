# Personal AI Assistant

A personal AI assistant with **one brain and several devices**: you talk to it in normal
language, and it performs real actions on your machines — then tells you what actually
happened.

> The name is not decided yet. It comes from a single setting (`APP_NAME` in
> `backend/.env`), which the API reports and the web client reads.

**Status: local milestone working.** Chat *and voice* with real tool calling, a Mac agent
that really opens apps and runs commands, confirmation for risky actions, a shared
conversation and an audit log. Everything runs on one machine: `docker compose up` gives
you one page to open. No iPhone app yet.

## What it can do today

- **Jarvis-style interface.** A full-screen living orb in the middle — red while you speak,
  green while it speaks — with the conversation history on the left and devices/activity
  on the right.
- **"Hey Jarvis" or two claps.** While the page is open it listens for its name (Chrome's
  speech recognition) and for a double clap (an audio-thread detector that ignores speech
  and single bangs). "Hey Jarvis, VS Code-u aç" works in one breath; what it heard is shown
  under the orb. "Sağ ol" / "yat" sends it back to sleep. On by default; the switch at the
  top turns it off.
- **Native Azerbaijani voice.** With `AZURE_SPEECH_KEY` set, the realtime model answers in
  text and every sentence is spoken by Azure's native `az-AZ-BabekNeural` (or Banu) voice
  as it streams; talking over it stops it at once. Without the key the realtime model
  speaks itself, with a foreign accent.
- **Use the Mac like a person.** Reads the screen (macOS OCR, text with click points),
  moves and clicks the mouse, scrolls, types any text (ə, ş, ç included) and presses
  shortcuts, looping look → act → look until the task is done. Needs Accessibility and
  Screen Recording permission for the agent's Python (the install script prints the path).
- **Code with Claude.** "xakker frontend-i VS Code-da aç, Claude ilə login bug-ını həll et"
  finds the project in `~/Projects` (asks if several match), opens it in VS Code and starts
  Claude Code with the task in a visible Terminal, with Claude's normal permission prompts.
- **Remember you, in Obsidian.** Facts go to `Jarvis/Memory.md` in your vault and are read
  into every conversation (text and voice); every turn is logged to
  `Jarvis/Conversations/YYYY-MM-DD.md`; it can search your whole vault. Edit the memory
  file yourself and it knows.

- **Talk normally, by text or by voice.** "Docker işləyir?" → it checks the real Docker on
  your Mac and answers. The microphone button opens a live, interruptible voice session.
- **Act on the Mac.** Open/quit apps (verified afterwards, and matched from whatever you
  called them — "termiusu ac" finds Termius), Docker and Git status, find files, open
  folders and URLs, run shell commands, and run commands in a **visible Terminal** window
  for ssh or anything interactive.
- **Understand how you actually write.** Informal Azerbaijani without diacritics, typos and
  voice transcripts; it asks you to repeat rather than guessing.
- **Refuse to lie.** It may only claim what a tool result says. A failure, a timeout or an
  offline device is reported as such.
- **Full access when you want it.** With `FULL_AUTONOMY=true`, shell, Terminal and
  AppleScript run straight away. Anything that looks destructive (`rm`, `sudo`, force
  push, shutdown, ...) still waits for your confirm button. With it off, every high-risk
  action waits.
- **Control the whole Mac.** AppleScript (any app, settings, notifications), volume, and
  system info (battery, Wi-Fi, disk, frontmost app).
- **Keep one conversation.** Any client joins the same thread, so context carries over.
- **Log everything.** Every executed action with arguments, result, error and duration.

## How it works

```text
   Browser (web dashboard)            Mac agent
          │ HTTP                          │ WebSocket (outbound only)
          └────────► BRAIN (FastAPI) ◄────┘
                          │
                     PostgreSQL
```

The brain does all the thinking. Devices only execute and report. Online devices'
capabilities become the tools the model can call, named by device type
(`mac_open_app`), so you never have to say which device you mean — and the model cannot
call a device that is offline.

More detail: [docs/architecture.md](docs/architecture.md).

## Technology

| Area | Stack |
| --- | --- |
| Brain | Python 3.12, FastAPI, Pydantic, WebSockets |
| Data | PostgreSQL 17, SQLAlchemy 2 (async, psycopg 3), Alembic |
| Model | OpenAI (Chat Completions + tool calling) behind an `AIService` interface |
| Web | Next.js 16 (App Router), TypeScript, Tailwind CSS 4 |
| Mac agent | Python (a native Swift app comes later) |
| Infra | Docker Compose |

## Project structure

```text
.
├── backend/                  # the brain
│   ├── app/
│   │   ├── ai/               # service, agent loop, assistant, confirmations, prompts
│   │   ├── agents/           # device connections + command bus
│   │   ├── devices/          # capability catalog, dispatcher, device registry
│   │   ├── memory/           # conversations, audit, long-term memory
│   │   ├── tools/            # backend-side tools
│   │   ├── api/              # routes, WebSocket, dependencies
│   │   ├── core/             # settings, security, logging
│   │   └── database/         # engine/session, ORM models
│   ├── alembic/              # migrations
│   └── tests/
├── web/                      # dashboard (chat, devices, activity)
├── agents/mac/               # the Mac agent
├── docs/
└── docker-compose.yml
```

## Quick start

```bash
cp backend/.env.example backend/.env   # paste your OPENAI_API_KEY
docker compose up --build -d           # postgres + brain + web
open http://localhost:3000
```

Then start the Mac agent, which cannot live in a container (see below):

```bash
cd agents/mac && ./install-autostart.sh   # starts now and at every login
# or, to run it by hand:  python3 agent.py
```

`docker compose down` stops everything; stopping Docker itself stops everything too.
The containers come back by themselves when Docker starts again.

Prefer running the brain outside Docker while developing? See
[docs/development.md](docs/development.md).

## Why the Mac agent is not in Docker

Docker on macOS runs inside a Linux VM, which cannot open applications, run
`osascript`, or see your screen. Anything that acts on the Mac must run on the Mac. So
the brain, the database and the web page are containers, and the agent is one small
process on the host that connects out to the brain. Stop Docker and the brain is gone, so
nothing can act — the agent just keeps retrying harmlessly.

## Environment variables

`backend/.env` (never committed):

| Variable | Description |
| --- | --- |
| `APP_NAME` | The assistant's display name. One place to rename it. |
| `APP_ENV` | `development` (default) or `production` (then `SECRET_KEY` is required) |
| `OPENAI_API_KEY` | Required for language understanding |
| `OPENAI_MODEL` | Defaults to `gpt-5.4-mini` |
| `DATABASE_URL` | e.g. `postgresql+psycopg://postgres:postgres@localhost:5432/personal_ai` |
| `SECRET_KEY` | For future token signing |
| `AGENT_TOKEN` | When set, device agents must present it |
| `REALTIME_MODEL` | Voice model, default `gpt-realtime-2.1`; `gpt-realtime-2.1-mini` is ~3x cheaper but hears and speaks Azerbaijani worse |
| `REALTIME_VOICE` | Voice, default `marin` |
| `VOICE_LANGUAGE` | Spoken language hint, default `az` |
| `OWNER_NAME` | Who the assistant is talking to |
| `CORS_ORIGINS` | JSON list of allowed browser origins |
| `OBSIDIAN_VAULT_PATH` | Obsidian vault for memory (outside Docker; compose mounts `OBSIDIAN_VAULT` from the repository `.env`) |
| `AZURE_SPEECH_KEY` | Azure Speech key for the native Azerbaijani voice (free tier: 500k characters/month) |
| `AZURE_SPEECH_REGION` | Region of that Speech resource, default `westeurope` |
| `AZURE_TTS_VOICE` | `az-AZ-BabekNeural` (male, default) or `az-AZ-BanuNeural` (female) |
| `FULL_AUTONOMY` | `true` runs high-risk actions without asking, except destructive-looking commands |

`web/.env.local` (optional): `NEXT_PUBLIC_API_URL`, the backend URL. It is public by
design — never put secrets in `NEXT_PUBLIC_*`.

The repository `.env` holds the Docker host ports (`POSTGRES_PORT`, `BACKEND_PORT`,
`WEB_PORT`), `OBSIDIAN_VAULT` (host path of the vault, mounted into the backend), `TZ`
(default `Asia/Baku`, for log times) and may hold `OPENAI_API_KEY`, which overrides
`backend/.env` for containers.

### Voice costs money per minute

Audio is billed per minute, unlike text. The default is the full realtime model because
the mini one misheard and mispronounced Azerbaijani; switch `REALTIME_MODEL` to
`gpt-realtime-2.1-mini` to pay ~3x less. A session closes itself after five minutes of
silence. Set a
monthly spend limit in the OpenAI dashboard, and do not leave the microphone on.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/` | API info, including the assistant's name |
| GET | `/health` | `{"status": "ok"}` |
| POST | `/api/v1/chat` | Send a message; returns the reply, executed actions and pending confirmations |
| POST | `/api/v1/voice/session` | Short-lived credential for a browser voice session |
| POST | `/api/v1/voice/tool` | A tool the voice model asked for (same gating as text) |
| POST | `/api/v1/voice/speak` | One sentence as native Azerbaijani speech (MP3) |
| POST | `/api/v1/voice/turn` | Store a spoken turn in the shared conversation |
| GET | `/api/v1/conversations` | Past conversations (history sidebar) |
| GET | `/api/v1/conversations/current` | The shared thread |
| GET | `/api/v1/conversations/{id}` | One past conversation |
| POST | `/api/v1/actions/{id}/confirm` | Run a held-back high-risk action |
| POST | `/api/v1/actions/{id}/cancel` | Drop it |
| GET | `/api/v1/devices` | Devices, live status, capabilities |
| GET | `/api/v1/tools` | Backend tools + online device capabilities |
| POST | `/api/v1/tools/{name}/execute` | Run one tool directly (for testing) |
| GET | `/api/v1/activity` | Audit log |
| WS | `/ws/devices` | Device agent channel |

## Security

Right now this is a **single-user, local-machine** system: `get_current_user` returns the
owner without checking anything, and the Mac agent can run shell commands. That is
acceptable while everything listens on localhost. Before the brain moves to a server:
real authentication, per-device credentials, and a stricter policy for `run_command`.
See the security section of [docs/architecture.md](docs/architecture.md).

## Roadmap

```text
[x] Project structure, FastAPI backend, database, migrations
[x] AI service abstraction (provider can be swapped)
[x] Tool registry + capability catalog with risk levels
[x] OpenAI function calling (real agent loop)
[x] Device agents over WebSocket + command bus with timeouts
[x] Mac Agent: applications, Docker, Git, files, shell
[x] Verified results — no invented success
[x] Confirmation for high-risk actions + audit log
[x] Shared rolling conversation
[x] Web dashboard: chat, devices, activity

[x] Voice: realtime, interruptible, same tools and conversation as text
[x] One-command Docker start + a single page to open

[x] Long-term memory in Obsidian, used by text and voice
[x] Jarvis UI: orb, history sidebar
[x] "Hey Jarvis" wake word (in the browser)
[ ] Native Mac app (menu bar, global hotkey, offline wake word)
[ ] Multi-step task UI (progress, cancel)
[ ] Real authentication + per-device pairing
[ ] Brain on a server, reachable from anywhere
[ ] iPhone: PWA first, then a native app with App Intents
[ ] Browser agent, GitHub integration
[ ] Proactive and scheduled tasks
```

## License

[MIT](LICENSE)
