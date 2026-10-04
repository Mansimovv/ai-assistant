"""Tools that let the model write to and search the owner's Obsidian vault."""

from typing import Any

from pydantic import Field

from app.memory.obsidian import ObsidianVault
from app.tools.base import Tool, ToolParameters


class RememberParameters(ToolParameters):
    fact: str = Field(
        description=(
            "One self-contained fact to keep, written in Azerbaijani, e.g. "
            "'Serverin ünvanı 10.0.0.5-dir, istifadəçi adı root'."
        )
    )


class Remember(Tool[RememberParameters]):
    name = "remember"
    description = (
        "Save a lasting fact about the owner (preferences, people, servers, projects, plans, "
        "anything they ask you to remember) to their Obsidian memory. It is shown to you in "
        "every future conversation."
    )
    parameters = RememberParameters

    def __init__(self, vault: ObsidianVault) -> None:
        self._vault = vault

    async def execute(self, params: RememberParameters) -> dict[str, Any]:
        self._vault.remember(params.fact)
        return {"saved": params.fact}


class SearchNotesParameters(ToolParameters):
    query: str = Field(description="Words to look for, e.g. 'server parol' or 'Bakı görüş'.")


class SearchNotes(Tool[SearchNotesParameters]):
    name = "search_notes"
    description = (
        "Search the owner's Obsidian notes and past conversation logs. Use it when they ask "
        "about something said or written before that is not in your memory."
    )
    parameters = SearchNotesParameters

    def __init__(self, vault: ObsidianVault) -> None:
        self._vault = vault

    async def execute(self, params: SearchNotesParameters) -> dict[str, Any]:
        results = self._vault.search(params.query)
        return {"count": len(results), "results": results}
