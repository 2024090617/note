"""Tests for session module."""

from digimate.session.session import Session
from digimate.session.budget import ContextBudgetManager
from digimate.session.compact import maybe_compact


def test_session_add_messages():
    s = Session()
    s.add_message("user", "hello")
    s.add_message("assistant", "hi")
    msgs = s.get_messages()
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].content == "hi"


def test_session_save_load(tmp_path):
    s = Session()
    s.add_message("user", "test")
    path = str(tmp_path / "session.json")
    s.save(path)
    loaded = Session.load(path)
    assert len(loaded.messages) == 1
    assert loaded.messages[0].content == "test"


def test_budget_manager():
    bm = ContextBudgetManager(context_window=10_000, response_reserve=1_000)
    assert bm.available == 9_000
    bm.record("system_prompt", "a" * 4_000)  # ~1000 tokens
    assert bm.total_used > 0
    assert not bm.is_over_budget()


def test_compact_when_over_budget():
    s = Session()
    bm = ContextBudgetManager(context_window=1000, response_reserve=200)
    # Add enough messages to exceed budget
    for i in range(20):
        s.add_message("user", f"message number {i} " * 50)
    bm.record("history", "\n".join(m.content for m in s.get_messages()))
    assert bm.is_over_budget()
    maybe_compact(s, bm)
    # After compaction, history should be shorter
    assert len(s.messages) < 20
