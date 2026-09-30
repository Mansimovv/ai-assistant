"""What device agents can do.

The catalog is defined here, on the brain, so there is one source of truth for
descriptions, argument schemas and risk. An agent announces which capability
*names* it implements when it connects; the brain builds the model's tool list
from that.

The model sees a capability as `<device type>_<capability>`, e.g. `mac_open_app`.
"""

from enum import StrEnum

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
