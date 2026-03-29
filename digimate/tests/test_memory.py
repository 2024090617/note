"""Tests for memory module."""

from digimate.memory.markdown import MarkdownMemory
from digimate.memory.working import WorkingMemory


def test_working_memory_notes():
    wm = WorkingMemory(max_items=10, max_tokens=5000)
    wm.add_note("key1", "value1", priority=1)
    wm.add_note("key2", "value2", priority=2)
    assert wm.get_note("key1").content == "value1"
    assert len(wm._notes) == 2


def test_working_memory_render():
    wm = WorkingMemory(max_items=10, max_tokens=5000)
    wm.add_note("finding", "The server uses port 8080")
    rendered = wm.render()
    assert "<working_memory>" in rendered
    assert "port 8080" in rendered


def test_working_memory_clear():
    wm = WorkingMemory()
    wm.add_note("a", "b")
    wm.clear()
    assert len(wm._notes) == 0


def test_working_memory_remove():
    wm = WorkingMemory()
    wm.add_note("key", "val")
    assert wm.remove_note("key")
    assert not wm.remove_note("key")


def test_working_memory_lru_eviction():
    wm = WorkingMemory(max_items=3)
    wm.add_note("a", "1", priority=1)
    wm.add_note("b", "2", priority=1)
    wm.add_note("c", "3", priority=1)
    wm.add_note("d", "4", priority=1)  # should evict 'a'
    assert wm.get_note("a") is None
    assert wm.get_note("d").content == "4"


def test_markdown_memory_init(tmp_path):
    mm = MarkdownMemory(str(tmp_path))
    mm.initialize()
    items = mm.list_memories()
    # Initially empty or has only discovered files
    assert isinstance(items, list)


def test_markdown_memory_store_recall(tmp_path):
    mm = MarkdownMemory(str(tmp_path))
    mm.initialize()
    mm.store("pytest uses --tb=short", "conventions")
    entries = mm.recall("pytest", limit=5)
    assert len(entries) >= 1
    assert "pytest" in entries[0].content


def test_markdown_memory_prompt_context(tmp_path):
    mm = MarkdownMemory(str(tmp_path))
    mm.initialize()
    mm.store("important convention", "general")
    ctx = mm.get_prompt_context(max_tokens=5000)
    assert isinstance(ctx, str)
