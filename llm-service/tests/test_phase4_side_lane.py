"""Tests for Phase 4 side-question lane lifecycle and eviction."""

from llm_service.agent.core import Agent, AgentConfig, AgentMode, AgentResponse


def _make_agent(tmp_path, side_lane_max_turns=3):
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
        side_lane_max_turns=side_lane_max_turns,
        side_lane_ttl_minutes=20,
    )
    return Agent(config)


def test_side_lane_starts_on_side_question(monkeypatch, tmp_path):
    agent = _make_agent(tmp_path)
    agent.session.set_goal("Implement retry logic")
    agent.session.set_focus_mode("strict-task")

    monkeypatch.setattr(
        agent,
        "_decide_interaction",
        lambda _text, force_task=False: {
            "mode": "side-question",
            "goal": agent.session.state.goal,
            "continuation": False,
            "continuation_note": "",
        },
    )
    monkeypatch.setattr(agent, "chat", lambda _text: "Side answer")

    outcome = agent.respond("What is the weather?")

    assert outcome["mode"] == "chat"
    assert agent.session.focus_mode == "task-with-side-questions"
    assert agent.session.side_lane.get("active") is True
    assert agent.session.side_lane.get("turns") == 1


def test_side_lane_evicts_by_turn_limit(monkeypatch, tmp_path):
    agent = _make_agent(tmp_path, side_lane_max_turns=1)
    agent.session.set_goal("Implement retry logic")
    agent.session.set_focus_mode("strict-task")

    monkeypatch.setattr(
        agent,
        "_decide_interaction",
        lambda _text, force_task=False: {
            "mode": "side-question",
            "goal": agent.session.state.goal,
            "continuation": False,
            "continuation_note": "",
        },
    )
    monkeypatch.setattr(agent, "chat", lambda _text: "Side answer")

    outcome = agent.respond("Unrelated question")

    assert "Side-question lane closed" in outcome["summary"]
    assert agent.session.focus_mode == "strict-task"
    assert agent.session.side_lane == {}


def test_task_turn_clears_side_lane(monkeypatch, tmp_path):
    agent = _make_agent(tmp_path)
    agent.session.set_goal("Implement retry logic")
    agent.session.start_side_lane("what is python")
    agent.session.set_focus_mode("task-with-side-questions")

    monkeypatch.setattr(
        agent,
        "_decide_interaction",
        lambda _text, force_task=False: {
            "mode": "task",
            "goal": "Implement retry logic",
            "continuation": True,
            "continuation_note": "continue",
        },
    )
    monkeypatch.setattr(
        agent,
        "run_task",
        lambda **kwargs: AgentResponse(is_complete=True, summary="resumed"),
    )

    outcome = agent.respond("continue")

    assert outcome["mode"] == "task"
    assert agent.session.side_lane == {}
    assert agent.session.focus_mode == "strict-task"
