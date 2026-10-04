"""What device agents can do.

The catalog is defined here, on the brain, so there is one source of truth for
descriptions, argument schemas and risk. An agent announces which capability
*names* it implements when it connects; the brain builds the model's tool list
from that.

The model sees a capability as `<device type>_<capability>`, e.g. `mac_open_app`.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.tools.base import ToolParameters


class Risk(StrEnum):
    LOW = "low"  # read-only or trivially reversible
    MEDIUM = "medium"  # changes something, still reversible
    HIGH = "high"  # needs explicit confirmation before it runs


class AppParameters(ToolParameters):
    name: str = Field(description="Application name as macOS knows it, e.g. 'Visual Studio Code'.")


class GitStatusParameters(ToolParameters):
    path: str = Field(description="Path to the git repository, e.g. '~/Projects/my-app'.")


class FindFilesParameters(ToolParameters):
    query: str = Field(description="Part of the file name to search for, e.g. 'invoice' or '.pdf'.")
    folder: str = Field(default="~/Downloads", description="Folder to search in.")
    limit: int = Field(default=20, ge=1, le=100)


class OpenPathParameters(ToolParameters):
    path: str = Field(description="File or folder path to reveal in Finder, or a URL to open.")


class RunCommandParameters(ToolParameters):
    command: str = Field(description="Shell command to run on the device.")


class RunInTerminalParameters(ToolParameters):
    command: str = Field(
        description=(
            "Command to run in a visible Terminal window, e.g. 'ssh user@host'. "
            "Use this for anything interactive or anything the user wants to watch."
        )
    )


class RunAppleScriptParameters(ToolParameters):
    script: str = Field(
        description=(
            "AppleScript source, e.g. 'tell application \"Music\" to play' or "
            "'display notification \"Hazırdır\" with title \"Jarvis\"'."
        )
    )


class SetVolumeParameters(ToolParameters):
    level: int = Field(ge=0, le=100, description="Output volume in percent, 0 mutes.")


class ClaudeCodeParameters(ToolParameters):
    project: str = Field(
        description="Project folder name as the user said it (e.g. 'ai assistant', 'sabah os frontend') or a path."
    )
    task: str = Field(
        description=(
            "What Claude should do in the project, as a clear, complete instruction, e.g. "
            "'Run the project, find why the login page crashes and fix it'."
        )
    )
    open_editor: bool = Field(default=True, description="Also open the project in VS Code.")


class PointParameters(ToolParameters):
    x: int = Field(ge=0, description="Screen x in points, as reported by look_at_screen.")
    y: int = Field(ge=0, description="Screen y in points, as reported by look_at_screen.")


class MouseClickParameters(PointParameters):
    button: Literal["left", "right"] = "left"
    double: bool = Field(default=False, description="Double-click (open a file, select a word).")


class ScrollParameters(ToolParameters):
    direction: Literal["up", "down"]
    amount: int = Field(default=5, ge=1, le=50, description="Lines to scroll.")
    x: int | None = Field(default=None, ge=0, description="Optional point to scroll at.")
    y: int | None = Field(default=None, ge=0)


class TypeTextParameters(ToolParameters):
    text: str = Field(description="Text to type into the focused field, any language.")


class PressKeysParameters(ToolParameters):
    keys: str = Field(
        description=(
            "A key or shortcut; several separated by spaces run in order. Examples: 'enter', "
            "'cmd+space', 'cmd+t', 'cmd+shift+4', 'tab tab enter'."
        )
    )


class Capability(BaseModel):
    name: str
    description: str
    parameters: type[ToolParameters]
    risk: Risk = Risk.LOW


CAPABILITIES: dict[str, Capability] = {
    capability.name: capability
    for capability in [
        Capability(
            name="open_app",
            description="Open an application and verify that it is actually running afterwards.",
            parameters=AppParameters,
        ),
        Capability(
            name="close_app",
            description="Quit an application.",
            parameters=AppParameters,
            risk=Risk.MEDIUM,
        ),
        Capability(
            name="app_status",
            description="Check whether an application is currently running.",
            parameters=AppParameters,
        ),
        Capability(
            name="docker_status",
            description="Check whether Docker is running and list running containers.",
            parameters=ToolParameters,
        ),
        Capability(
            name="git_status",
            description="Show the branch and uncommitted changes of a git repository.",
            parameters=GitStatusParameters,
        ),
        Capability(
            name="find_files",
            description="Find files by name inside a folder.",
            parameters=FindFilesParameters,
        ),
        Capability(
            name="open_path",
            description="Open a file, folder or URL with the default application.",
            parameters=OpenPathParameters,
        ),
        Capability(
            name="list_apps",
            description="List the applications installed on the device.",
            parameters=ToolParameters,
        ),
        Capability(
            name="run_in_terminal",
            description=(
                "Open Terminal on the device and run a command there, visibly, so the user can "
                "see and keep using it. This is how to connect to a server (ssh), watch logs, or "
                "run anything interactive. The user must confirm it before it runs."
            ),
            parameters=RunInTerminalParameters,
            risk=Risk.HIGH,
        ),
        Capability(
            name="system_info",
            description="Battery, volume, Wi-Fi network, free disk space, frontmost app and uptime.",
            parameters=ToolParameters,
        ),
        Capability(
            name="set_volume",
            description="Set the output volume.",
            parameters=SetVolumeParameters,
        ),
        Capability(
            name="run_applescript",
            description=(
                "Run AppleScript on the device: control any application (Music, Safari, Finder, "
                "Mail, Notes, Messages...), system settings, notifications, keystrokes. "
                "Returns the script's result."
            ),
            parameters=RunAppleScriptParameters,
            risk=Risk.HIGH,
        ),
        Capability(
            name="list_projects",
            description="List the user's project folders (~/Projects and similar).",
            parameters=ToolParameters,
        ),
        Capability(
            name="claude_code",
            description=(
                "Work on a software project with Claude Code: finds the project by name, opens it "
                "in VS Code and starts Claude Code with the task in a visible Terminal, where it "
                "edits code, installs and runs things. Use for 'Claude ilə həll et', 'layihəni "
                "işlət', 'bu bug-ı düzəlt', 'kodu yaz'."
            ),
            parameters=ClaudeCodeParameters,
            risk=Risk.HIGH,
        ),
        Capability(
            name="look_at_screen",
            description=(
                "See the screen: a screenshot to look at (with a coordinate grid), every visible "
                "text with the x,y point to click it, and the named buttons, fields and links of "
                "the frontmost window with their click points. Call it before clicking and again "
                "afterwards to check what happened."
            ),
            parameters=ToolParameters,
        ),
        Capability(
            name="mouse_click",
            description="Move the mouse to a point and click (left, right or double).",
            parameters=MouseClickParameters,
            risk=Risk.MEDIUM,
        ),
        Capability(
            name="mouse_move",
            description="Move the mouse pointer to a point without clicking (e.g. to hover).",
            parameters=PointParameters,
            risk=Risk.MEDIUM,
        ),
        Capability(
            name="scroll",
            description="Scroll up or down, optionally at a point.",
            parameters=ScrollParameters,
            risk=Risk.MEDIUM,
        ),
        Capability(
            name="type_text",
            description="Type text with the keyboard into whatever is focused.",
            parameters=TypeTextParameters,
            risk=Risk.HIGH,
        ),
        Capability(
            name="press_keys",
            description="Press a key or keyboard shortcut (enter, cmd+space, cmd+c, ...).",
            parameters=PressKeysParameters,
            risk=Risk.HIGH,
        ),
        Capability(
            name="run_command",
            description=(
                "Run a shell command on the device. Use only when no other capability fits; "
                "the user must confirm it before it runs."
            ),
            parameters=RunCommandParameters,
            risk=Risk.HIGH,
        ),
    ]
}
