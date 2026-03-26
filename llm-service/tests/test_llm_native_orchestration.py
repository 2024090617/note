"""Tests for LLM-native turn orchestration and focus behavior."""

from llm_service.agent.core import Agent, AgentConfig, AgentMode, AgentResponse
from llm_service.agent.core.prompt import CHAT_ASSISTANT_SYSTEM_PROMPT
from llm_service.agent.tools.types import ToolResult


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeChatClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def chat(self, messages, model=None):
        if not self.responses:
            raise RuntimeError("No fake responses left")
        return _FakeResponse(self.responses.pop(0))


def _make_agent(tmp_path, **kwargs):
    config = AgentConfig(
        mode=AgentMode.COPILOT,
        model="gpt-4o-mini",
        workdir=str(tmp_path),
        log_dir=str(tmp_path / "logs"),
        log_to_file=False,
        log_to_console=False,
        memory_strategy="none",
        mcp_config_path=None,
        intent_router="llm",
        **kwargs,
    )
    return Agent(config)


def test_respond_routes_task(monkeypatch, tmp_path):
    agent = _make_agent(tmp_path)

    def fake_run_task(task, max_iterations=None, preserve_state=False, continuation_note=None):
        assert task == "Refactor the parser module"
        assert preserve_state is False
        return AgentResponse(is_complete=True, summary="task complete")

    monkeypatch.setattr(agent, "_decide_interaction", lambda _text, force_task=False: {
        "mode": "task",
        "goal": "Refactor the parser module",
        "continuation": False,
        "continuation_note": "",
    })
    monkeypatch.setattr(agent, "run_task", fake_run_task)

    outcome = agent.respond("please do it")

    assert outcome["mode"] == "task"
    assert outcome["summary"] == "task complete"
    assert agent.session.focus_mode == "strict-task"
    assert agent.session.task_anchor["objective"] == "Refactor the parser module"


def test_respond_handles_side_question(monkeypatch, tmp_path):
    agent = _make_agent(tmp_path)
    agent.session.set_goal("Implement auth retries")
    agent.session.set_focus_mode("strict-task")

    monkeypatch.setattr(agent, "_decide_interaction", lambda _text, force_task=False: {
        "mode": "side-question",
        "goal": agent.session.state.goal,
        "continuation": False,
        "continuation_note": "",
    })
    monkeypatch.setattr(agent, "chat", lambda _text: "Python was created by Guido van Rossum.")

    outcome = agent.respond("who created python?")

    assert outcome["mode"] == "chat"
    assert "Active task remains: Implement auth retries" in outcome["summary"]
    assert agent.session.focus_mode == "task-with-side-questions"


def test_respond_force_task(monkeypatch, tmp_path):
    agent = _make_agent(tmp_path)

    monkeypatch.setattr(agent, "run_task", lambda *args, **kwargs: AgentResponse(is_complete=True, summary="ok"))
    outcome = agent.respond("Run tests and fix failures", force_task=True)

    assert outcome["mode"] == "task"
    assert outcome["decision"]["source"] == "forced"


def test_extract_json_object_accepts_fenced_json(tmp_path):
    agent = _make_agent(tmp_path)
    data = agent._extract_json_object(
        """```json\n{"mode": "task", "confidence": 0.9}\n```"""
    )

    assert data is not None
    assert data["mode"] == "task"


def test_normalize_observation_truncates_large_output(tmp_path):
    agent = _make_agent(tmp_path)
    content = "A" * (agent.config.max_tool_output_chars + 4000)

    normalized = agent._normalize_observation("mcp_call_tool", content)

    assert "truncated" in normalized
    assert len(normalized) < len(content)


def test_run_task_updates_short_memory(monkeypatch, tmp_path):
    agent = _make_agent(tmp_path)

    monkeypatch.setattr(
        agent,
        "_get_llm_response",
        lambda: AgentResponse(is_complete=True, thought="done", summary="ok"),
    )

    agent.run_task("Implement retry logic")

    summary = agent.session.short_memory.get("summary", "")
    assert "Goal: Implement retry logic" in summary
    assert "Milestone: Task completed" in summary


def test_curated_chat_messages_use_chat_system_prompt(tmp_path):
    agent = _make_agent(tmp_path)

    messages = agent._build_curated_chat_messages("Explain retries briefly")

    assert messages
    assert messages[0].role == "system"
    assert messages[0].content == CHAT_ASSISTANT_SYSTEM_PROMPT


def test_chat_can_use_internal_planner_for_web_summary(monkeypatch, tmp_path):
    agent = _make_agent(tmp_path)
    agent._client = _FakeChatClient(
        [
            '{"use_tool": true, "tool": "read_online_content", "arguments": {"url": "https://example.com"}, "reason": "needs live page"}',
            "Here is a concise summary of the fetched page.",
        ]
    )

    monkeypatch.setattr(
        agent.tools,
        "read_online_content",
        lambda url: ToolResult(True, "Example Domain content", data={"url": url}),
    )

    reply = agent.chat("read this page https://example.com and summarize")

    assert "summary" in reply.lower()


def test_chat_falls_back_to_plain_response_when_planner_fails(tmp_path):
    agent = _make_agent(tmp_path)
    agent._client = _FakeChatClient(
        [
            "not-json",
            "Direct conversational answer without tool use.",
        ]
    )

    reply = agent.chat("can you summarize this page https://example.com?")

    assert "conversational" in reply.lower()


def test_chat_planner_can_be_disabled_by_policy(monkeypatch, tmp_path):
    agent = _make_agent(tmp_path, chat_planner_max_tool_calls_per_turn=0)
    agent._client = _FakeChatClient(["Final response without tool call."])

    called = {"count": 0}

    def _fake_read(url):
        called["count"] += 1
        return ToolResult(True, "unused")

    monkeypatch.setattr(agent.tools, "read_online_content", _fake_read)

    reply = agent.chat("read this page https://example.com and summarize")

    assert "final response" in reply.lower()
    assert called["count"] == 0


def test_chat_planner_respects_allowed_tool_list(monkeypatch, tmp_path):
    agent = _make_agent(tmp_path, chat_planner_allowed_tools=[])
    agent._client = _FakeChatClient(
        [
            '{"use_tool": true, "tool": "read_online_content", "arguments": {"url": "https://example.com"}}',
            "Response generated without executing blocked tool.",
        ]
    )

    called = {"count": 0}

    def _fake_read(url):
        called["count"] += 1
        return ToolResult(True, "unused")

    monkeypatch.setattr(agent.tools, "read_online_content", _fake_read)

    reply = agent.chat("please fetch https://example.com and summarize")

    assert "blocked tool" in reply.lower()
    assert called["count"] == 0
