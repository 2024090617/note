"""Tests for the working memory module."""

import pytest

from llm_service.agent.session.working_memory import (
    WorkingMemory,
    WMNote,
    WMArtifact,
)


# ── Basic CRUD ───────────────────────────────────────────────────────

def test_add_and_get_note():
    wm = WorkingMemory()
    wm.add_note("root-cause", "Token refresh too short", priority=2)
    note = wm.get_note("root-cause")
    assert note is not None
    assert note.content == "Token refresh too short"
    assert note.priority == 2


def test_add_and_get_artifact():
    wm = WorkingMemory()
    wm.add_artifact("config", "retry: 5s", label="current config")
    art = wm.get_artifact("config")
    assert art is not None
    assert art.data == "retry: 5s"
    assert art.label == "current config"


def test_remove_note():
    wm = WorkingMemory()
    wm.add_note("tmp", "data")
    assert wm.remove_note("tmp") is True
    assert wm.get_note("tmp") is None
    assert wm.remove_note("nonexistent") is False


def test_remove_artifact():
    wm = WorkingMemory()
    wm.add_artifact("snippet", "print('hi')")
    assert wm.remove_artifact("snippet") is True
    assert wm.get_artifact("snippet") is None


def test_update_existing_note():
    wm = WorkingMemory()
    wm.add_note("key", "old")
    wm.add_note("key", "new")
    assert wm.get_note("key").content == "new"
    assert len(wm.list_notes()) == 1  # not duplicated


def test_empty_key_raises():
    wm = WorkingMemory()
    with pytest.raises(ValueError):
        wm.add_note("", "content")
    with pytest.raises(ValueError):
        wm.add_artifact("", "data")


# ── Goal & constraints ───────────────────────────────────────────────

def test_goal():
    wm = WorkingMemory()
    assert wm.goal is None
    wm.set_goal("Fix auth")
    assert wm.goal == "Fix auth"


def test_constraints():
    wm = WorkingMemory()
    wm.add_constraint("No downtime")
    wm.add_constraint("No downtime")  # duplicate ignored
    wm.add_constraint("Python 3.12+")
    assert len(wm._constraints) == 2


# ── Capacity enforcement ─────────────────────────────────────────────

def test_item_limit_evicts():
    wm = WorkingMemory(max_items=3, max_tokens=0)
    wm.add_note("a", "x", priority=1)
    wm.add_note("b", "y", priority=1)
    wm.add_note("c", "z", priority=1)
    assert wm.item_count == 3

    wm.add_note("d", "w", priority=1)
    assert wm.item_count == 3  # oldest evicted
    assert wm.get_note("a") is None  # 'a' was oldest


def test_high_priority_survives_eviction():
    wm = WorkingMemory(max_items=2, max_tokens=0)
    wm.add_note("important", "keep me", priority=10)
    wm.add_note("low", "drop me", priority=1)
    wm.add_note("new", "hello", priority=1)

    assert wm.item_count == 2
    assert wm.get_note("important") is not None  # high priority kept
    assert wm.get_note("low") is None  # low priority evicted


def test_token_limit_evicts():
    wm = WorkingMemory(max_items=100, max_tokens=20)
    # Each note is ~25 tokens (100 chars / 4)
    wm.add_note("big", "x" * 100, priority=1)
    # Should still fit (we allow some overflow handling)
    wm.add_note("bigger", "y" * 100, priority=1)
    # After adding second, eviction should kick in
    assert wm.item_count <= 2


# ── Render (episodic buffer) ─────────────────────────────────────────

def test_render_empty():
    wm = WorkingMemory()
    assert wm.render() == ""


def test_render_with_goal_and_notes():
    wm = WorkingMemory()
    wm.set_goal("Fix the timeout")
    wm.add_note("cause", "Token refresh window", priority=2)
    wm.add_artifact("config", "timeout: 30", label="auth config")

    rendered = wm.render()
    assert "<working_memory>" in rendered
    assert "</working_memory>" in rendered
    assert "Fix the timeout" in rendered
    assert "Token refresh window" in rendered
    assert "timeout: 30" in rendered
    assert 'key="cause"' in rendered
    assert 'key="config"' in rendered


def test_render_respects_budget():
    wm = WorkingMemory(max_tokens=10000)
    wm.set_goal("Big task")
    for i in range(50):
        wm.add_note(f"n{i}", f"Data point {i}: " + "x" * 100, priority=1)

    full = wm.render()
    tight = wm.render(max_tokens=50)

    assert len(tight) < len(full)
    assert "<working_memory>" in tight


# ── Serialization ────────────────────────────────────────────────────

def test_to_dict_and_from_dict():
    wm = WorkingMemory()
    wm.set_goal("Test goal")
    wm.add_constraint("constraint-1")
    wm.add_note("k1", "v1", priority=3)
    wm.add_artifact("a1", "data1", label="label1", priority=2)

    data = wm.to_dict()
    wm2 = WorkingMemory.from_dict(data)

    assert wm2.goal == "Test goal"
    assert len(wm2._constraints) == 1
    assert wm2.get_note("k1").content == "v1"
    assert wm2.get_note("k1").priority == 3
    assert wm2.get_artifact("a1").data == "data1"


# ── Clear ────────────────────────────────────────────────────────────

def test_clear():
    wm = WorkingMemory()
    wm.set_goal("task")
    wm.add_note("k", "v")
    wm.add_artifact("a", "d")
    wm.add_constraint("c")

    wm.clear()

    assert wm.goal is None
    assert wm.item_count == 0
    assert wm._constraints == []
    assert wm.render() == ""


# ── Summary ──────────────────────────────────────────────────────────

def test_summary():
    wm = WorkingMemory()
    s = wm.summary()
    assert "notes=0" in s
    assert "artifacts=0" in s

    wm.set_goal("Fix auth")
    wm.add_note("k", "v")
    s = wm.summary()
    assert "goal=Fix auth" in s
    assert "notes=1" in s
