#!/usr/bin/env python3
"""Mac agent.

Keeps a WebSocket open to the backend, announces what it can do, then executes
capabilities on this Mac and reports back what really happened.

    python3 agent.py --server ws://localhost:8000/ws/devices

Requires: pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import difflib
import json
import logging
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import websockets

logger = logging.getLogger("mac-agent")

DEFAULT_TIMEOUT = 10
COMMAND_TIMEOUT = 15
OUTPUT_LIMIT = 4000
VERIFY_ATTEMPTS = 6  # ~3 seconds
APP_FOLDERS = ("/Applications", "/System/Applications", "/Applications/Utilities")
PROJECT_FOLDERS = ("~/Projects", "~/Developer", "~/Desktop", "~/Documents", "~/code")

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


def projects() -> list[Path]:
    """Folders that look like projects: direct children of the usual project folders."""
    found: list[Path] = []
    for folder in PROJECT_FOLDERS:
        directory = expand(folder)
        if directory.is_dir():
            found.extend(
                child for child in sorted(directory.iterdir()) if child.is_dir() and not child.name.startswith((".", "_"))
            )
    return found


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def resolve_project(name: str) -> tuple[Path | None, list[str]]:
    """Find a project from what the user said: "sabah os frontend" -> sabah-os-web-frontend.

    Returns the match, or no match plus the candidates so the model can ask which one.
    """
    path = expand(name)
    if path.is_dir():
        return path, []
    all_projects = projects()
    words = [_normalize(word) for word in re.split(r"[\s_\-.]+", name.lower()) if _normalize(word)]
    words = [word for word in words if word not in ("layihe", "layihesi", "proyekt", "project", "papka")]
    if not words:
        return None, [project.name for project in all_projects]

    def matching(candidate_words: list[str]) -> list[Path]:
        return [p for p in all_projects if all(word in _normalize(p.name) for word in candidate_words)]

    # Azerbaijani glues suffixes on: "ai-assistanti", "xakkerin" are not part of the name.
    trimmed = [re.sub(r"(nin|nun|in|un|ni|nu|i|u)$", "", word) or word for word in words]
    for candidate_words in (words, trimmed):
        exact = [p for p in all_projects if _normalize(p.name) == "".join(candidate_words)]
        if len(exact) == 1:
            return exact[0], []
        found = matching(candidate_words)
        if len(found) == 1:
            return found[0], []
        if found:
            return None, [p.name for p in found]
    close = difflib.get_close_matches("".join(words), [_normalize(p.name) for p in all_projects], n=3, cutoff=0.6)
    matches = [p for p in all_projects if _normalize(p.name) in close]
    if len(matches) == 1:
        return matches[0], []
    return None, [p.name for p in matches]


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


async def run_applescript(script: str) -> tuple[bool, Any, str | None, bool]:
    try:
        result = run(["osascript", "-e", script], timeout=COMMAND_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, None, f"AppleScript timed out after {COMMAND_TIMEOUT}s", True
    if result.returncode != 0:
        error = clip(result.stderr.strip())
        if "-1743" in error or "not authorized" in error.lower():
            error = (
                "macOS blocked it: allow this agent to control that app in "
                "System Settings > Privacy & Security > Automation, then try again"
            )
        return False, {"script": script}, error or "AppleScript failed", True
    return True, {"result": clip(result.stdout.strip())}, None, True


async def system_info() -> tuple[bool, Any, str | None, bool]:
    def output(command: list[str]) -> str:
        try:
            return run(command).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return ""

    battery = output(["pmset", "-g", "batt"]).splitlines()
    disk = shutil.disk_usage(Path.home())
    wifi = output(["networksetup", "-getairportnetwork", "en0"]).removeprefix("Current Wi-Fi Network: ")
    data = {
        "battery": battery[1].split("\t")[-1] if len(battery) > 1 else None,
        "volume_percent": output(["osascript", "-e", "output volume of (get volume settings)"]),
        "wifi": None if not wifi or "not associated" in wifi else wifi,
        "disk_free_gb": round(disk.free / 1e9, 1),
        "frontmost_app": output(
            ["osascript", "-e", 'tell application "System Events" to name of first process whose frontmost is true']
        ),
        "uptime": output(["uptime"]),
    }
    return True, data, None, True


async def set_volume(level: int) -> tuple[bool, Any, str | None, bool]:
    result = run(["osascript", "-e", f"set volume output volume {int(level)}"])
    if result.returncode != 0:
        return False, None, clip(result.stderr.strip()) or "Could not set the volume", True
    actual = run(["osascript", "-e", "output volume of (get volume settings)"]).stdout.strip()
    return True, {"volume_percent": actual}, None, True


async def list_projects() -> tuple[bool, Any, str | None, bool]:
    found = projects()
    return True, {"count": len(found), "projects": [str(path) for path in found]}, None, True


async def claude_code(project: str, task: str, open_editor: bool = True) -> tuple[bool, Any, str | None, bool]:
    """Open the project in VS Code and start Claude Code on it in a visible Terminal.

    Claude keeps its normal permission prompts, so the user approves risky steps in
    the Terminal window and can stop it at any time.
    """
    path, candidates = resolve_project(project)
    if path is None:
        if candidates:
            return False, {"candidates": candidates}, f"Several projects match '{project}'; ask which one", True
        return False, None, f"No project called '{project}' in {', '.join(PROJECT_FOLDERS)}", True
    if shutil.which("claude") is None and not (Path.home() / ".local/bin/claude").exists():
        return False, None, "Claude Code is not installed (the `claude` command is missing)", True

    if open_editor:
        run(["open", "-a", "Visual Studio Code", str(path)])
    ok, _, error, _ = await run_in_terminal(f"cd {shlex.quote(str(path))} && claude {shlex.quote(task)}")
    if not ok:
        return False, {"project": str(path)}, error, True
    return True, {"project": str(path), "task": task, "note": "Claude Code is working in a visible Terminal window"}, None, False


# --- screen, mouse, keyboard ------------------------------------------------
# Coordinates are screen points of the main display, origin top-left, exactly as
# look_at_screen reports them, so the model can click what it read.

OCR_LIMIT = 250
ELEMENT_LIMIT = 200
ELEMENT_SECONDS = 1.5
GRID_STEP = 100
SCREENSHOT_QUALITY = 0.55
# Things a person can click, type into or choose; the rest of the tree is layout.
INTERACTIVE_ROLES = {
    "AXButton", "AXLink", "AXTextField", "AXTextArea", "AXSearchField", "AXCheckBox",
    "AXRadioButton", "AXPopUpButton", "AXMenuButton", "AXMenuItem", "AXMenuBarItem", "AXTab",
    "AXComboBox", "AXSlider", "AXDisclosureTriangle", "AXCell", "AXRow", "AXImage", "AXStaticText",
}
SETTINGS_ACCESSIBILITY = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
SETTINGS_SCREEN = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
PYTHON_BINARY = os.path.realpath(sys.executable)

# macOS virtual key codes (ANSI layout).
KEY_CODES = {
    **{letter: code for letter, code in zip("asdfhgzxcv", (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), strict=True)},
    **{letter: code for letter, code in zip("bqweryt", (11, 12, 13, 14, 15, 16, 17), strict=True)},
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27,
    "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "l": 37, "j": 38,
    "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47, "`": 50,
    "enter": 36, "return": 36, "tab": 48, "space": 49, "backspace": 51, "delete": 51,
    "escape": 53, "esc": 53, "forwarddelete": 117, "home": 115, "end": 119, "pageup": 116,
    "pagedown": 121, "left": 123, "right": 124, "down": 125, "up": 126,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}


def _input_allowed() -> str | None:
    """None when this process may post mouse and keyboard events, else why not."""
    import ApplicationServices

    if ApplicationServices.AXIsProcessTrusted():
        return None
    run(["open", SETTINGS_ACCESSIBILITY])
    return (
        "macOS has not allowed mouse/keyboard control yet. In System Settings > Privacy & Security > "
        f"Accessibility, turn on: {PYTHON_BINARY} (I just opened that page), then try again"
    )


def _screen_allowed() -> str | None:
    import Quartz

    if Quartz.CGPreflightScreenCaptureAccess():
        return None
    Quartz.CGRequestScreenCaptureAccess()
    run(["open", SETTINGS_SCREEN])
    return (
        "macOS has not allowed screen reading yet. In System Settings > Privacy & Security > "
        f"Screen & System Audio Recording, turn on: {PYTHON_BINARY}, then restart the agent"
    )


def _screen_size() -> tuple[int, int]:
    import Quartz

    bounds = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
    return int(bounds.size.width), int(bounds.size.height)


def _recognize_text(image: str, width: int, height: int) -> list[dict[str, Any]]:
    import Vision
    from Foundation import NSURL

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    # No Azerbaijani model exists; Turkish covers most of its letters.
    request.setRecognitionLanguages_(["tr-TR", "en-US", "ru-RU"])
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(image), None)
    handler.performRequests_error_([request], None)

    found = []
    for observation in request.results() or []:
        candidate = observation.topCandidates_(1)
        if not candidate:
            continue
        box = observation.boundingBox()  # normalized, origin bottom-left
        found.append(
            {
                "text": str(candidate[0].string()),
                "x": round((box.origin.x + box.size.width / 2) * width),
                "y": round((1 - box.origin.y - box.size.height / 2) * height),
            }
        )
    found.sort(key=lambda item: (item["y"] // 10, item["x"]))  # reading order
    return found[:OCR_LIMIT]


def _annotated_screenshot(image: str, width: int, height: int) -> str:
    """The screenshot at screen-point size with a labelled grid, as base64 JPEG.

    Pixel (x, y) of this image is screen point (x, y), so whatever the model sees it
    can click; the grid lets it read coordinates off icons that have no text.
    """
    from AppKit import (
        NSBezierPath,
        NSBitmapImageRep,
        NSCalibratedRGBColorSpace,
        NSColor,
        NSFont,
        NSFontAttributeName,
        NSBackgroundColorAttributeName,
        NSForegroundColorAttributeName,
        NSGraphicsContext,
        NSImage,
        NSImageCompressionFactor,
        NSJPEGFileType,
        NSMakeRect,
        NSString,
    )

    source = NSImage.alloc().initWithContentsOfFile_(image)
    canvas = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, width, height, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0
    )
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(NSGraphicsContext.graphicsContextWithBitmapImageRep_(canvas))
    source.drawInRect_(NSMakeRect(0, 0, width, height))

    NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.1, 0.4, 0.35).set()
    for x in range(GRID_STEP, width, GRID_STEP):
        NSBezierPath.strokeLineFromPoint_toPoint_((x, 0), (x, height))
    for y in range(GRID_STEP, height, GRID_STEP):
        NSBezierPath.strokeLineFromPoint_toPoint_((0, height - y), (width, height - y))
    label = {
        NSFontAttributeName: NSFont.boldSystemFontOfSize_(10),
        NSForegroundColorAttributeName: NSColor.whiteColor(),
        NSBackgroundColorAttributeName: NSColor.colorWithCalibratedRed_green_blue_alpha_(0.85, 0.0, 0.3, 0.8),
    }
    # AppKit draws from the bottom-left; labels show top-left screen coordinates.
    for x in range(GRID_STEP, width, GRID_STEP):
        for y in range(GRID_STEP, height, GRID_STEP):
            NSString.stringWithString_(f"{x},{y}").drawAtPoint_withAttributes_((x + 2, height - y - 13), label)
    NSGraphicsContext.restoreGraphicsState()

    data = canvas.representationUsingType_properties_(NSJPEGFileType, {NSImageCompressionFactor: SCREENSHOT_QUALITY})
    return base64.b64encode(bytes(data)).decode("ascii")


def _attribute(element: Any, name: str) -> Any:
    import ApplicationServices as AS

    error, value = AS.AXUIElementCopyAttributeValue(element, name, None)
    return value if error == 0 else None


def _ui_elements() -> list[dict[str, Any]] | None:
    """Named, clickable things in the frontmost window, with the point to click them.

    None when macOS has not granted Accessibility access.
    """
    import ApplicationServices as AS
    from AppKit import NSWorkspace

    if not AS.AXIsProcessTrusted():
        return None
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return []
    root = AS.AXUIElementCreateApplication(app.processIdentifier())
    AS.AXUIElementSetMessagingTimeout(root, 0.5)
    # Chrome and Electron apps (VS Code, Slack, WhatsApp) only expose their web content
    # to assistive apps that ask for it.
    AS.AXUIElementSetAttributeValue(root, "AXManualAccessibility", True)
    window = _attribute(root, "AXFocusedWindow") or _attribute(root, "AXMainWindow")
    if window is None:
        return []

    deadline = time.monotonic() + ELEMENT_SECONDS
    found: list[dict[str, Any]] = []
    queue = [window]
    while queue and len(found) < ELEMENT_LIMIT and time.monotonic() < deadline:
        element = queue.pop(0)
        queue.extend(_attribute(element, "AXChildren") or [])
        role = _attribute(element, "AXRole")
        if role not in INTERACTIVE_ROLES:
            continue
        name = next(
            (
                str(value).strip()
                for value in (
                    _attribute(element, "AXTitle"),
                    _attribute(element, "AXDescription"),
                    _attribute(element, "AXPlaceholderValue"),
                    _attribute(element, "AXValue") if role in ("AXStaticText", "AXTextField", "AXSearchField") else None,
                )
                if isinstance(value, str) and value.strip()
            ),
            "",
        )
        position, size = _attribute(element, "AXPosition"), _attribute(element, "AXSize")
        if not name or position is None or size is None:
            continue
        _, point = AS.AXValueGetValue(position, AS.kAXValueTypeCGPoint, None)
        _, extent = AS.AXValueGetValue(size, AS.kAXValueTypeCGSize, None)
        if extent.width <= 0 or extent.height <= 0:
            continue
        found.append(
            {
                "role": role.removeprefix("AX"),
                "name": name[:80],
                "x": round(point.x + extent.width / 2),
                "y": round(point.y + extent.height / 2),
            }
        )
    return found


async def look_at_screen() -> tuple[bool, Any, str | None, bool]:
    """What a person would see: a screenshot, the text on it, and the clickable elements."""
    if error := _screen_allowed():
        return False, None, error, True
    width, height = _screen_size()
    with tempfile.TemporaryDirectory() as folder:
        image = os.path.join(folder, "screen.png")
        result = run(["screencapture", "-x", "-m", "-t", "png", image])
        if result.returncode != 0 or not os.path.exists(image):
            return False, None, clip(result.stderr.strip()) or "Could not capture the screen", True
        texts = await asyncio.to_thread(_recognize_text, image, width, height)
        screenshot = _annotated_screenshot(image, width, height)
    elements = _ui_elements()
    _, front, _, _ = await system_info()
    data = {
        "screen": {"width": width, "height": height},
        "frontmost_app": front["frontmost_app"],
        "texts": texts,
        "elements": elements if elements is not None else "unavailable: Accessibility permission missing",
        "screenshot": f"data:image/jpeg;base64,{screenshot}",
    }
    return True, data, None, True


def _mouse_event(kind: int, x: float, y: float, button: int, clicks: int = 1) -> None:
    import Quartz

    event = Quartz.CGEventCreateMouseEvent(None, kind, (x, y), button)
    Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventClickState, clicks)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


async def mouse_move(x: int, y: int) -> tuple[bool, Any, str | None, bool]:
    import Quartz

    if error := _input_allowed():
        return False, None, error, True
    _mouse_event(Quartz.kCGEventMouseMoved, x, y, Quartz.kCGMouseButtonLeft)
    return True, {"x": x, "y": y}, None, False


async def mouse_click(x: int, y: int, button: str = "left", double: bool = False) -> tuple[bool, Any, str | None, bool]:
    import Quartz

    if error := _input_allowed():
        return False, None, error, True
    if button == "right":
        down, up, code = Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp, Quartz.kCGMouseButtonRight
    else:
        down, up, code = Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp, Quartz.kCGMouseButtonLeft
    _mouse_event(Quartz.kCGEventMouseMoved, x, y, code)
    await asyncio.sleep(0.05)
    for clicks in (1, 2) if double else (1,):
        _mouse_event(down, x, y, code, clicks)
        _mouse_event(up, x, y, code, clicks)
        await asyncio.sleep(0.05)
    return True, {"clicked": {"x": x, "y": y}, "button": button, "double": double}, None, False


async def scroll(direction: str, amount: int = 5, x: int | None = None, y: int | None = None) -> tuple[bool, Any, str | None, bool]:
    import Quartz

    if error := _input_allowed():
        return False, None, error, True
    if x is not None and y is not None:
        _mouse_event(Quartz.kCGEventMouseMoved, x, y, Quartz.kCGMouseButtonLeft)
    lines = amount if direction == "up" else -amount
    event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1, lines)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
    return True, {"scrolled": direction, "amount": amount}, None, False


async def type_text(text: str) -> tuple[bool, Any, str | None, bool]:
    """Type any text, including ə, ş, ç and emoji, regardless of the keyboard layout."""
    import Quartz

    if error := _input_allowed():
        return False, None, error, True
    for character in text:
        for is_down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(None, 0, is_down)
            Quartz.CGEventKeyboardSetUnicodeString(event, len(character.encode("utf-16-le")) // 2, character)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(0.008)
    return True, {"typed": len(text)}, None, False


async def press_keys(keys: str) -> tuple[bool, Any, str | None, bool]:
    """A key or shortcut: "enter", "cmd+space", "cmd+shift+4", "ctrl+c"."""
    import Quartz

    if error := _input_allowed():
        return False, None, error, True
    modifiers = {
        "cmd": Quartz.kCGEventFlagMaskCommand, "command": Quartz.kCGEventFlagMaskCommand,
        "shift": Quartz.kCGEventFlagMaskShift,
        "alt": Quartz.kCGEventFlagMaskAlternate, "option": Quartz.kCGEventFlagMaskAlternate,
        "ctrl": Quartz.kCGEventFlagMaskControl, "control": Quartz.kCGEventFlagMaskControl,
        "fn": Quartz.kCGEventFlagMaskSecondaryFn,
    }
    for combo in keys.lower().split():
        *held, key = [part.strip() for part in combo.split("+")]
        if key not in KEY_CODES or any(part not in modifiers for part in held):
            return False, None, f"Unknown key in '{combo}'", True
        flags = 0
        for part in held:
            flags |= modifiers[part]
        for is_down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(None, KEY_CODES[key], is_down)
            Quartz.CGEventSetFlags(event, flags)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        await asyncio.sleep(0.05)
    return True, {"pressed": keys}, None, False


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
    "run_applescript": run_applescript,
    "system_info": system_info,
    "set_volume": set_volume,
    "list_projects": list_projects,
    "claude_code": claude_code,
    "look_at_screen": look_at_screen,
    "mouse_move": mouse_move,
    "mouse_click": mouse_click,
    "scroll": scroll,
    "type_text": type_text,
    "press_keys": press_keys,
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
