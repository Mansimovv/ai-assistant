"""Long-term memory lives in the owner's Obsidian vault as plain Markdown."""

from pathlib import Path

import pytest

from app.ai.prompts import build_system_prompt
from app.memory.obsidian import ObsidianVault
from app.tools.registry import create_default_registry


def test_remembered_facts_are_markdown_and_reach_the_prompt(tmp_path: Path) -> None:
    vault = ObsidianVault(str(tmp_path))

    vault.remember("Serverin ünvanı 10.0.0.5-dir")

    note = (tmp_path / "Jarvis" / "Memory.md").read_text(encoding="utf-8")
    assert "- Serverin ünvanı 10.0.0.5-dir" in note
    assert "10.0.0.5" in build_system_prompt("Jarvis", "", "Maharram", vault.memory())


def test_turns_are_logged_to_a_daily_note(tmp_path: Path) -> None:
    vault = ObsidianVault(str(tmp_path))

    vault.log_turn("user", "Docker işləyir?")
    vault.log_turn("assistant", "Bəli, işləyir.")

    [note] = (tmp_path / "Jarvis" / "Conversations").glob("*.md")
    text = note.read_text(encoding="utf-8")
    assert text.index("Docker işləyir?") < text.index("Bəli, işləyir.")


def test_search_finds_the_owners_own_notes_but_not_obsidian_settings(tmp_path: Path) -> None:
    (tmp_path / "Layihələr.md").write_text("Sabah server parolunu dəyiş", encoding="utf-8")
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian" / "x.md").write_text("server", encoding="utf-8")

    results = ObsidianVault(str(tmp_path)).search("server parol")

    assert [result["note"] for result in results] == ["Layihələr.md"]
    assert "parol" in results[0]["snippet"]


def test_missing_vault_disables_memory_quietly(tmp_path: Path) -> None:
    vault = ObsidianVault(str(tmp_path / "nope"))

    vault.remember("x")
    vault.log_turn("user", "x")

    assert not vault.enabled
    assert vault.memory() == ""
    assert {tool.name for tool in create_default_registry(vault).list_tools()} == {"get_current_time", "echo"}


@pytest.mark.anyio
async def test_memory_tools_write_and_search_the_vault(tmp_path: Path) -> None:
    registry = create_default_registry(ObsidianVault(str(tmp_path)))

    await registry.execute("remember", {"fact": "Qəhvəni şəkərsiz içir"})
    found = await registry.execute("search_notes", {"query": "qəhvəni"})

    assert found["count"] == 1


def test_friend_style_is_only_added_when_asked_for() -> None:
    assert "Swearing" not in build_system_prompt("Jarvis", "", "Maharram")
    assert "Swearing" in build_system_prompt("Jarvis", "", "Maharram", style="friend")
