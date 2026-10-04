"""Long-term memory kept in the owner's Obsidian vault.

Plain Markdown, so the owner can read and edit everything the assistant knows:

    <vault>/Jarvis/Memory.md                    facts about the owner, loaded into every prompt
    <vault>/Jarvis/Conversations/YYYY-MM-DD.md  a daily log of what was said

`search` looks through the whole vault, so the owner's own notes are usable too.
Without a configured vault every method is a harmless no-op.
"""

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

FOLDER = "Jarvis"
MEMORY_FILE = "Memory.md"
CONVERSATIONS_FOLDER = "Conversations"
MEMORY_HEADER = (
    "# Yaddaş\n\n"
    "Jarvis-in sən haqqında bildikləri. Bu faylı özün də redaktə edə bilərsən — "
    "hər söhbətdə oxunur.\n\n"
)
# The memory file goes into every prompt; keep the newest part if it grows huge.
MEMORY_PROMPT_LIMIT = 8000
SEARCH_RESULT_LIMIT = 8
SNIPPET_RADIUS = 160


class ObsidianVault:
    def __init__(self, path: str | None) -> None:
        self._root = Path(path).expanduser() if path else None
        if self._root is not None and not self._root.is_dir():
            logger.warning("Obsidian vault %s does not exist; memory is disabled", self._root)
            self._root = None

    @property
    def enabled(self) -> bool:
        return self._root is not None

    def memory(self) -> str:
        """What the assistant knows about the owner, for the system prompt."""
        if self._root is None:
            return ""
        path = self._root / FOLDER / MEMORY_FILE
        if not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8").strip()
        return text[-MEMORY_PROMPT_LIMIT:]

    def remember(self, fact: str) -> None:
        if self._root is None:
            return
        path = self._root / FOLDER / MEMORY_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(MEMORY_HEADER, encoding="utf-8")
        with path.open("a", encoding="utf-8") as file:
            file.write(f"- {fact.strip()} _({datetime.now():%Y-%m-%d})_\n")

    def log_turn(self, role: str, text: str) -> None:
        """Append one spoken or typed turn to today's conversation note."""
        if self._root is None or not text.strip():
            return
        now = datetime.now()
        path = self._root / FOLDER / CONVERSATIONS_FOLDER / f"{now:%Y-%m-%d}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(f"# Söhbətlər — {now:%Y-%m-%d}\n\n", encoding="utf-8")
        speaker = "**Sən**" if role == "user" else "**Jarvis**"
        with path.open("a", encoding="utf-8") as file:
            file.write(f"{speaker} ({now:%H:%M}): {text.strip()}\n\n")

    def search(self, query: str) -> list[dict[str, str]]:
        """Notes containing the query's words (case-insensitive), best and newest first."""
        words = [word for word in query.lower().split() if len(word) >= 3] or query.lower().split()
        if self._root is None or not words:
            return []
        scored: list[tuple[int, float, Path, int, str]] = []
        for path in self._root.rglob("*.md"):
            if ".obsidian" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            lowered = text.lower()
            hits = [lowered.find(word) for word in words if word in lowered]
            if hits:
                scored.append((len(hits), path.stat().st_mtime, path, min(hits), text))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [
            {
                "note": str(path.relative_to(self._root)),
                "snippet": text[max(0, index - SNIPPET_RADIUS) : index + SNIPPET_RADIUS].strip(),
            }
            for _, _, path, index, text in scored[:SEARCH_RESULT_LIMIT]
        ]
