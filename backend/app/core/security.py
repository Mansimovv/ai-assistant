"""Authentication and permission primitives.

Personal AI runs in single-user local mode for now: the API is only reachable
from this machine and every request is treated as the owner. `get_current_user`
is the one place real authentication (e.g. tokens signed with SECRET_KEY) plugs
in; every /api/v1 route already depends on it.
"""

from dataclasses import dataclass
from enum import StrEnum


class Permission(StrEnum):
    """What an action is allowed to do. Every tool declares the one it needs."""

    READ = "read"  # read files, screen contents, calendar, ...
    WRITE = "write"  # create or modify data
    EXECUTE = "execute"  # run commands or programs
    MESSAGE = "message"  # send messages or emails on the user's behalf
    SYSTEM = "system"  # control a device: apps, keyboard, mouse, settings
    ADMIN = "admin"  # manage Personal AI itself


@dataclass(frozen=True)
class User:
    id: str


LOCAL_OWNER = User(id="owner")


async def get_current_user() -> User:
    return LOCAL_OWNER
