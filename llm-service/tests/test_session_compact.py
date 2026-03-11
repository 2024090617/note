"""Tests for session compaction."""

from llm_service.agent.session.session import Session


def test_compact_summarises_old_messages():
    session = Session()
    # Add 10 messages (5 user + 5 assistant)
    for i in range(10):
        role = "user" if i % 2 == 0 else "assistant"
        session.add_message(role, f"Message {i}: " + "x" * 100)

    original_count = len(session.messages)
    assert original_count == 10

    summary = session.compact(keep_recent=4)

    assert summary != ""  # compaction happened
    # Should have 1 summary + 4 recent = 5
    assert len(session.messages) == 5
    assert session.messages[0].role == "user"
    assert "[Conversation summary" in session.messages[0].content
    assert session._compaction_count == 1


def test_compact_noop_when_few_messages():
    session = Session()
    session.add_message("user", "hello")
    session.add_message("assistant", "hi")

    summary = session.compact(keep_recent=4)
    assert summary == ""
    assert len(session.messages) == 2  # unchanged


def test_estimate_history_tokens():
    session = Session()
    session.add_message("user", "a" * 400)
    session.add_message("assistant", "b" * 400)

    tokens = session.estimate_history_tokens()
    assert tokens == 200  # 800 chars / 4


def test_compact_all_when_keep_zero():
    session = Session()
    for i in range(8):
        session.add_message("user", f"msg {i}")

    summary = session.compact(keep_recent=0)
    assert summary != ""
    assert len(session.messages) == 1  # only the summary
