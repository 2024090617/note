"""Tests for topic isolation in chat context building."""

from llm_service.agent.core import Agent, AgentConfig, AgentMode


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeClient:
    def __init__(self):
        self.calls = []

    def chat(self, messages, model=None):
        self.calls.append({"messages": messages, "model": model})
        return _FakeResponse("ok")


def _make_agent(tmp_path):
    config = AgentConfig(
        mode=AgentMode.COPILOT,
        model="gpt-4o-mini",
        workdir=str(tmp_path),
        log_dir=str(tmp_path / "logs"),
        log_to_file=False,
        log_to_console=False,
        memory_strategy="none",
        mcp_config_path=None,
        context_recent_messages=4,
        context_retrieval_limit=3,
    )
    return Agent(config)


def test_chat_topic_shift_isolates_history(monkeypatch, tmp_path):
    agent = _make_agent(tmp_path)
    fake_client = _FakeClient()
    agent._client = fake_client

    # First message in default topic
    agent.chat("How do I write unit tests in Python?")

    # Force next turn to start a new topic thread.
    monkeypatch.setattr(agent.topic_detector, "is_topic_shift", lambda _prev, _curr: True)
    agent.chat("What is a healthy vegan breakfast plan?")

    second_call = fake_client.calls[-1]["messages"]
    combined = "\n".join(m.content for m in second_call)

    assert "unit tests in Python" not in combined
    assert "vegan breakfast plan" in combined


def test_chat_respects_current_thread_focus(tmp_path):
    agent = _make_agent(tmp_path)
    fake_client = _FakeClient()
    agent._client = fake_client

    first = agent.session.create_thread("python", switch=True)
    agent.session.add_message("user", "Python typing tips", thread_id=first["id"])
    second = agent.session.create_thread("cooking", switch=True)
    agent.session.add_message("user", "Pasta sauce ideas", thread_id=second["id"])

    messages = agent._build_curated_chat_messages("quick dinner")
    combined = "\n".join(m.content for m in messages)

    assert "Pasta sauce ideas" in combined
    assert "Python typing tips" not in combined
