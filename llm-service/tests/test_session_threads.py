"""Tests for thread-aware session behavior."""

from llm_service.agent.session import Session


def test_session_creates_default_thread():
    session = Session()

    assert session.current_thread_id is not None
    assert len(session.threads) == 1
    assert session.threads[0]["topic"] == "general"


def test_session_thread_round_trip(tmp_path):
    session = Session()
    session.create_thread("backend-api", switch=True)
    session.add_message("user", "Discuss API auth")
    session.set_focus("all")

    path = tmp_path / "session_threads.json"
    session.save(path)

    loaded = Session.load(path)
    assert len(loaded.threads) == 2
    assert loaded.current_thread_id == session.current_thread_id
    assert loaded.focus_thread_id == "all"
    assert loaded.messages[-1].thread_id == session.current_thread_id
    loaded_thread = loaded.get_current_thread()
    assert loaded_thread is not None
    assert loaded_thread.get("summary_pinned") is False


def test_thread_summary_updates_from_recent_messages():
    session = Session()
    thread = session.create_thread("api-design", switch=True)

    session.add_message("user", "Need consistent endpoint naming")
    session.add_message("assistant", "Use plural nouns and versioned prefix")

    current = session.get_current_thread()
    assert current is not None
    assert current["id"] == thread["id"]
    assert "Need consistent endpoint naming" in current.get("summary", "")
    assert "Use plural nouns" in current.get("summary", "")


def test_manual_pinned_summary_is_not_overwritten_by_auto_updates():
    session = Session()
    thread = session.create_thread("security", switch=True)

    ok = session.set_thread_summary("Pinned security decisions", thread_id=thread["id"], pinned=True)
    assert ok is True

    session.add_message("user", "rotate keys every 30 days")
    current = session.get_current_thread()
    assert current is not None
    assert current.get("summary") == "Pinned security decisions"
    assert current.get("summary_pinned") is True


def test_auto_summary_can_be_restored_after_unpinning():
    session = Session()
    thread = session.create_thread("platform", switch=True)
    session.set_thread_summary("Pinned platform summary", thread_id=thread["id"], pinned=True)

    session.add_message("user", "improve deployment speed")
    session.set_thread_summary_pinned(False, thread_id=thread["id"])
    generated = session.update_thread_summary(thread_id=thread["id"], force=True)

    assert "improve deployment speed" in generated
    current = session.get_current_thread()
    assert current is not None
    assert current.get("summary_pinned") is False
