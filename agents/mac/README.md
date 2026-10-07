# Mac Agent

A small program that runs on this Mac, keeps a WebSocket open to the backend, and
executes what the assistant asks for — then reports what **really** happened.

The agent never decides anything. All reasoning lives in the backend; the agent only
runs capabilities and returns results.

## Run it

```bash
./install-autostart.sh     # recommended: runs now and at every login
./uninstall-autostart.sh   # remove it again
```

The installer creates its own virtualenv, writes a LaunchAgent
(`~/Library/LaunchAgents/com.local.assistant-agent.plist`) and logs to
`~/Library/Logs/assistant-agent.log`. It reads `BACKEND_PORT` from the repository `.env`.

By hand instead:

```bash
pip install -r requirements.txt          # only needs `websockets`
python3 agent.py --server ws://localhost:8001/ws/devices
```

**This cannot run in Docker.** A container on macOS lives in a Linux VM and cannot open
applications, run `osascript`, or see the screen.

Options (also available as environment variables):

| Option | Default | Meaning |
| --- | --- | --- |
| `--server` | `ws://localhost:8000/ws/devices` | Backend WebSocket URL (`AGENT_SERVER`) |
| `--device-id` | `mac` | Stable id of this device (`AGENT_DEVICE_ID`) |
| `--name` | hostname | Display name (`AGENT_DEVICE_NAME`) |
| `--token` | none | Required when the backend sets `AGENT_TOKEN` |

It reconnects by itself if the backend restarts.

## Capabilities

| Capability | Risk | What it does |
| --- | --- | --- |
| `open_app` | low | `open -a <name>`, then verifies the app is really running |
| `close_app` | medium | Quits the app, then verifies it stopped |
| `app_status` | low | Whether an app is running |
| `docker_status` | low | Docker version and running containers |
| `git_status` | low | Branch and uncommitted changes of a repository |
| `find_files` | low | Find files by name in a folder (max depth 4) |
| `open_path` | low | Open a file, folder or URL |
| `list_apps` | low | Every application installed on this Mac |
| `media` | low | Spotify/Music: play, pause, next, previous, now playing, search; reports the real player state |
| `read_ui` | low | Any app's window as text (every browser too): buttons, links, fields as `[ref] role "name"` plus visible text. No screenshot; needs only Accessibility |
| `ui_press` | medium | Press an element by ref (AXPress, or a click on its centre) |
| `ui_type` | medium | Put text into a field by ref (sets the value, or types straight into that app), optionally Enter; checks the field really holds it |
| `run_in_terminal` | **high** | Open Terminal and run a command **visibly** — ssh to a server, tail logs, anything interactive |
| `run_command` | **high** | Any shell command, invisibly (output returned to the assistant) |

## Application names

The agent matches whatever the user said against the applications actually installed:
`termiusu` → `Termius`, `app storeni` → `App Store`, `vs code` → `Visual Studio Code`.
Azerbaijani suffixes are stripped, then exact, prefix, substring and fuzzy matching are
tried in that order. The resolved name is reported back, and the app list is sent to the
backend on connect so speech recognition expects those names too.

An app that opens and immediately quits (needs login, crashes) is reported as a failure —
never as "opened".

Every result carries `ok` and, where the agent checked the real state afterwards,
`verified: true`. A failure is returned as a failure; the agent never reports success
it did not observe.

## macOS permissions

The first time some capabilities run, macOS asks for permission:

- `close_app` and `run_in_terminal` send Apple Events → **Automation** permission
  (Terminal is listed separately from other apps).
- Future screen/input capabilities will need **Screen Recording** and **Accessibility**.

Grant these in System Settings → Privacy & Security. They are tied to the program's
signature: running the agent from a different Python binary asks again.

## Security

- `run_command` gives the assistant a shell on this Mac. The backend classifies it as
  high risk and will not run it without explicit confirmation in the UI.
- Set `AGENT_TOKEN` on both sides once the backend is reachable from anywhere but this
  machine.
- The agent makes an outbound connection only: nothing listens on this Mac.

## Later

- Native Swift app: menu bar, global hotkey, wake word, notifications.
- More capabilities: screenshots, window/UI control, browser automation.
