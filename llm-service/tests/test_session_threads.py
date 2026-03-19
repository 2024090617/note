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
