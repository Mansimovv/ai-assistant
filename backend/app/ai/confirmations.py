"""Actions that wait for the user's explicit confirmation.

High-risk capabilities (shell commands, for example) are never executed by the
model on its own: the brain parks them here and only runs them after the user
confirms in the UI. Kept in memory on purpose — a pending action must not
survive a restart.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from app.devices.capabilities import Risk

TTL = timedelta(minutes=10)


class PendingAction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: uuid.UUID
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk: Risk
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PendingActions:
    def __init__(self) -> None:
        self._actions: dict[str, PendingAction] = {}

    def add(self, conversation_id: uuid.UUID, tool: str, arguments: dict[str, Any], risk: Risk) -> PendingAction:
        self._expire()
        action = PendingAction(conversation_id=conversation_id, tool=tool, arguments=arguments, risk=risk)
        self._actions[action.id] = action
        return action

    def take(self, action_id: str) -> PendingAction | None:
        """Return the action and remove it, so it can only run once."""
        self._expire()
        return self._actions.pop(action_id, None)

    def _expire(self) -> None:
        cutoff = datetime.now(UTC) - TTL
        for action_id, action in list(self._actions.items()):
            if action.created_at < cutoff:
                del self._actions[action_id]


pending_actions = PendingActions()
