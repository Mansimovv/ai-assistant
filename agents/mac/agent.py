#!/usr/bin/env python3
"""Mac agent.

Keeps a WebSocket open to the backend, announces what it can do, then executes
capabilities on this Mac and reports back what really happened.

    python3 agent.py --server ws://localhost:8000/ws/devices

Requires: pip install websockets
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import logging
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

import websockets

logger = logging.getLogger("mac-agent")

DEFAULT_TIMEOUT = 10
COMMAND_TIMEOUT = 15
OUTPUT_LIMIT = 4000
VERIFY_ATTEMPTS = 6  # ~3 seconds
APP_FOLDERS = ("/Applications", "/System/Applications", "/Applications/Utilities")

# Spoken or typed shortcuts that fuzzy matching alone would not get right.
APP_ALIASES = {
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "code": "Visual Studio Code",
    "chrome": "Google Chrome",
    "brauzer": "Safari",
    "browser": "Safari",
}


def run(command: list[str], timeout: int = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


def installed_apps() -> list[str]:
    """Every application on this Mac, by display name."""
    names: set[str] = set()
    for folder in APP_FOLDERS:
        directory = Path(folder)
        if not directory.is_dir():
            continue
        for app in directory.glob("*.app"):
            names.add(app.stem)
        for app in directory.glob("*/*.app"):  # e.g. /Applications/Utilities/*
            names.add(app.stem)
    home_apps = Path.home() / "Applications"
    if home_apps.is_dir():
        names.update(app.stem for app in home_apps.glob("*.app"))
    return sorted(names)


def resolve_app(name: str) -> str:
    """Turn what the user said into a real application name.

    "termiusu", "termius", "TERMIUS" -> "Termius". Without this, a small spelling
    difference makes the whole request fail.
    """
    wanted = name.strip().strip('"').lower()
    apps = installed_apps()
    lookup = {app.lower(): app for app in apps}

    if wanted in lookup:
        return lookup[wanted]
    if wanted in APP_ALIASES and APP_ALIASES[wanted].lower() in lookup:
        return lookup[APP_ALIASES[wanted].lower()]

    # Azerbaijani glues suffixes onto names: "termiusu", "safarini", "app storeni".
    trimmed = re.sub(r"(nı|ni|nu|nü|yı|yi|yu|yü|ı|i|u|ü)$", "", wanted)
    for candidate in (wanted, trimmed):
        if candidate in lookup:
            return lookup[candidate]
        starts = [app for app in apps if app.lower().startswith(candidate)]
        if len(starts) == 1:
            return starts[0]
        contains = [app for app in apps if candidate in app.lower()]
        if len(contains) == 1:
            return contains[0]

    close = difflib.get_close_matches(wanted, [app.lower() for app in apps], n=1, cutoff=0.7)
    if close:
        return lookup[close[0]]
    return name  # let macOS decide, and report its error


def is_running(app: str) -> bool:
    result = run(["osascript", "-e", f'application "{app}" is running'])
    return result.stdout.strip() == "true"


def expand(path: str) -> Path:
    return Path(os.path.expandvars(path)).expanduser()


def clip(text: str) -> str:
    return text if len(text) <= OUTPUT_LIMIT else text[:OUTPUT_LIMIT] + "\n…(truncated)"


# --- capabilities ------------------------------------------------------------
# Every handler returns (ok, data, error, verified). `verified` means the agent
# checked the real state afterwards instead of trusting the command's exit code.


async def open_app(name: str) -> tuple[bool, Any, str | None, bool]:
    app = resolve_app(name)
    result = run(["open", "-a", app])
    if result.returncode != 0:
        return False, {"app": app}, clip(result.stderr.strip()) or f"Could not open {app}", True

    started = False
    for _ in range(VERIFY_ATTEMPTS):
        if is_running(app):
            started = True
            break
        await asyncio.sleep(0.5)
    if not started:
        return False, {"app": app, "running": False}, f"{app} did not start", True

    # Some apps launch and quit again (login needed, crash). Check it is still there,
    # so we never report a window the user cannot see.
    await asyncio.sleep(1.5)
    if not is_running(app):
        return (
            False,
            {"app": app, "running": False},
            f"{app} opened and closed again immediately",
            True,
        )
    return True, {"app": app, "running": True, "asked_for": name}, None, True


async def close_app(name: str) -> tuple[bool, Any, str | None, bool]:
    name = resolve_app(name)
    if not is_running(name):
        return True, {"app": name, "running": False, "note": "was not running"}, None, True
    result = run(["osascript", "-e", f'quit app "{name}"'])
    if result.returncode != 0:
        return False, None, clip(result.stderr.strip()) or f"Could not quit {name}", True
    for _ in range(VERIFY_ATTEMPTS):
        if not is_running(name):
            return True, {"app": name, "running": False}, None, True
        await asyncio.sleep(0.5)
    return False, {"app": name, "running": True}, f"{name} is still running", True


async def app_status(name: str) -> tuple[bool, Any, str | None, bool]:
    app = resolve_app(name)
    return True, {"app": app, "running": is_running(app)}, None, True


async def list_apps() -> tuple[bool, Any, str | None, bool]:
    apps = installed_apps()
    return True, {"count": len(apps), "apps": apps}, None, True


async def docker_status() -> tuple[bool, Any, str | None, bool]:
    if shutil.which("docker") is None:
        return False, None, "docker is not installed", True
    info = run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=15)
    if info.returncode != 0:
        return True, {"docker_running": False, "detail": clip(info.stderr.strip())}, None, True
    containers = run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"], timeout=15)
    running = [
        dict(zip(("name", "status"), line.split("\t", 1), strict=False))
        for line in containers.stdout.strip().splitlines()
        if line
    ]
    return True, {"docker_running": True, "version": info.stdout.strip(), "containers": running}, None, True


async def git_status(path: str) -> tuple[bool, Any, str | None, bool]:
    repository = expand(path)
    if not repository.is_dir():
        return False, None, f"{repository} is not a directory", True
    result = run(["git", "-C", str(repository), "status", "--short", "--branch"])
    if result.returncode != 0:
        return False, None, clip(result.stderr.strip()) or "git failed", True
    lines = result.stdout.splitlines()
    branch = lines[0].removeprefix("## ") if lines else ""
    changes = lines[1:]
    return True, {"path": str(repository), "branch": branch, "changes": changes, "clean": not changes}, None, True


async def find_files(query: str, folder: str = "~/Downloads", limit: int = 20) -> tuple[bool, Any, str | None, bool]:
    directory = expand(folder)
    if not directory.is_dir():
        return False, None, f"{directory} is not a directory", True
    result = run(
        ["find", str(directory), "-maxdepth", "4", "-iname", f"*{query}*", "-not", "-name", ".*"],
        timeout=DEFAULT_TIMEOUT,
    )
    files = [line for line in result.stdout.splitlines() if line][:limit]
    return True, {"folder": str(directory), "query": query, "count": len(files), "files": files}, None, True


async def open_path(path: str) -> tuple[bool, Any, str | None, bool]:
    target = path if path.startswith(("http://", "https://")) else str(expand(path))
    result = run(["open", target])
    if result.returncode != 0:
        return False, None, clip(result.stderr.strip()) or f"Could not open {target}", True
    return True, {"opened": target}, None, False


async def run_command(command: str) -> tuple[bool, Any, str | None, bool]:
    try:
        result = run(["/bin/zsh", "-lc", command], timeout=COMMAND_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, None, f"Command timed out after {COMMAND_TIMEOUT}s", True
    data = {
        "command": command,
        "exit_code": result.returncode,
        "stdout": clip(result.stdout.strip()),
        "stderr": clip(result.stderr.strip()),
    }
    return result.returncode == 0, data, None if result.returncode == 0 else f"exit code {result.returncode}", True


async def run_in_terminal(command: str) -> tuple[bool, Any, str | None, bool]:
    """Open Terminal and run a command there, visibly.

    This is how interactive things work: ssh into a server, tail a log, run a REPL.
    The output stays on screen for the user; we only confirm the window opened.
    """
    script = (
        'tell application "Terminal"\n'
        '  activate\n'
        f'  do script "{command.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"\n'
        'end tell'
    )
    result = run(["osascript", "-e", script], timeout=DEFAULT_TIMEOUT)
    if result.returncode != 0:
        error = clip(result.stderr.strip())
        if "-1743" in error or "not authorized" in error.lower():
            error = (
                "macOS blocked it: allow this agent to control Terminal in "
                "System Settings > Privacy & Security > Automation, then try again"
            )
        return False, {"command": command}, error or "Could not open Terminal", True
    return True, {"command": command, "note": "running in a visible Terminal window"}, None, False


HANDLERS = {
    "open_app": open_app,
    "close_app": close_app,
    "app_status": app_status,
    "docker_status": docker_status,
    "git_status": git_status,
    "find_files": find_files,
    "open_path": open_path,
    "list_apps": list_apps,
    "run_command": run_command,
    "run_in_terminal": run_in_terminal,
}


# --- connection --------------------------------------------------------------


async def execute(capability: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handler = HANDLERS.get(capability)
    if handler is None:
        return {"ok": False, "error": f"Unknown capability: {capability}", "verified": False}
    try:
        ok, data, error, verified = await handler(**arguments)
    except TypeError as exc:
        return {"ok": False, "error": f"Bad arguments: {exc}", "verified": False}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Command timed out", "verified": False}
    except Exception as exc:  # never lie about success
        logger.exception("Capability %s failed", capability)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "verified": False}
    return {"ok": ok, "data": data, "error": error, "verified": verified}


async def session(url: str, device_id: str, name: str, token: str | None) -> None:
    async with websockets.connect(url) as socket_connection:
        await socket_connection.send(
            json.dumps(
                {
                    "type": "register",
                    "device": {"id": device_id, "name": name, "type": "mac"},
                    "capabilities": sorted(HANDLERS),
                    "apps": installed_apps(),
                    "token": token,
                }
            )
        )
        greeting = json.loads(await socket_connection.recv())
        logger.info("Registered as %s, accepted capabilities: %s", device_id, greeting.get("capabilities"))

        async for raw in socket_connection:
            message = json.loads(raw)
            if message.get("type") != "invoke":
                continue
            capability = message.get("capability", "")
            logger.info("→ %s %s", capability, message.get("arguments"))
            result = await execute(capability, message.get("arguments") or {})
            logger.info("← ok=%s %s", result["ok"], result.get("error") or "")
            await socket_connection.send(json.dumps({"type": "result", "call_id": message["call_id"], **result}))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Mac agent")
    parser.add_argument("--server", default=os.environ.get("AGENT_SERVER", "ws://localhost:8000/ws/devices"))
    parser.add_argument("--device-id", default=os.environ.get("AGENT_DEVICE_ID", "mac"))
    parser.add_argument("--name", default=os.environ.get("AGENT_DEVICE_NAME", socket.gethostname().split(".")[0]))
    parser.add_argument("--token", default=os.environ.get("AGENT_TOKEN") or None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Connecting to %s as %s (%s)", args.server, args.name, args.device_id)

    while True:  # keep trying: the backend may restart
        try:
            await session(args.server, args.device_id, args.name, args.token)
        except (OSError, websockets.exceptions.WebSocketException) as exc:
            logger.warning("Connection lost (%s); retrying in 3s", exc)
        except asyncio.CancelledError:
            raise
        await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
