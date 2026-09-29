# Mac Agent (placeholder)

This folder will hold the **Mac Agent**: a small program that runs locally on macOS,
connects to the Personal AI backend and carries out actions on the Mac.

Nothing is implemented yet. This README records the plan and the contract the
backend already expects.

## Future responsibilities

- open and close applications
- read the screen and take screenshots
- keyboard and mouse input
- run terminal commands
- file operations
- browser operations

## How it will talk to the backend

The agent opens a WebSocket to `ws://<backend>/ws/devices` and registers itself
with its first message:

```json
{"type": "register", "device": {"id": "macbook-pro", "name": "MacBook Pro", "type": "mac"}}
```

The backend replies `{"type": "registered"}`, stores the device, and shows it as
**online** for as long as the socket stays open. Commands from the backend and their
results will travel over this same socket (not defined yet).

On the backend side, see `backend/app/api/websocket.py` and `backend/app/agents/`.

## Safety requirements (before any real action is added)

- Authenticate the agent (a device token) before accepting commands.
- Every action maps to a permission level (`READ`, `WRITE`, `EXECUTE`, `MESSAGE`,
  `SYSTEM`, `ADMIN`) defined in `backend/app/core/security.py`.
- Dangerous actions (running commands, deleting files, sending messages) require
  explicit user confirmation.
- macOS privacy permissions (Accessibility, Screen Recording) are requested by the
  agent, never bypassed.
