"""Tests for task continuation via checkpoints and resume-aware execution."""

from llm_service.agent.core import Agent, AgentConfig, AgentMode, AgentResponse
from llm_service.agent.session import Session


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
    )
    return Agent(config)


def test_session_checkpoint_round_trip(tmp_path):
    """Session checkpoints survive save/load and preserve key fields."""
    session = Session()
    session.set_goal("Improve onboarding flow")
    session.add_message("user", "Start planning")

    checkpoint = session.create_checkpoint(
        "manual",
        working_memory={"goal": "Improve onboarding flow", "notes": []},
        metadata={"source": "test"},
    )

    save_path = tmp_path / "session.json"
    session.save(save_path)

    loaded = Session.load(save_path)
    loaded_cp = loaded.get_checkpoint(checkpoint["id"])

    assert loaded_cp is not None
    assert loaded_cp["label"] == "manual"
    assert loaded_cp["goal"] == "Improve onboarding flow"
    assert loaded_cp["metadata"]["source"] == "test"


def test_agent_resume_checkpoint_restores_state_and_working_memory(tmp_path):
    """Resuming a checkpoint restores goal/plan and working memory snapshot."""
    agent = _make_agent(tmp_path)

    agent.session.set_goal("Fix flaky test suite")
    agent.session.state.plan = ["find flaky tests", "stabilize timing"]
    agent.session.state.plan_step = 1
    agent.working_memory.set_goal("Fix flaky test suite")
    agent.working_memory.add_note("flaky", "test_api_retry is timing sensitive")

    checkpoint = agent.create_checkpoint("manual")

    agent.session.set_goal("Different goal")
    agent.session.state.plan = []
    agent.working_memory.clear()

    restored = agent.resume_checkpoint(checkpoint["id"])

    assert restored["id"] == checkpoint["id"]
    assert agent.session.state.goal == "Fix flaky test suite"
    assert agent.session.state.plan == ["find flaky tests", "stabilize timing"]
    assert agent.working_memory.goal == "Fix flaky test suite"
    assert agent.working_memory.get_note("flaky") is not None


def test_run_task_preserve_state_keeps_existing_goal(monkeypatch, tmp_path):
    """Continuation mode should not reset previous task state."""
    agent = _make_agent(tmp_path)
    agent.session.set_goal("Original task goal")
    agent.session.state.plan = ["step 1", "step 2"]
    agent.working_memory.set_goal("Original task goal")

    monkeypatch.setattr(
        agent,
        "_get_llm_response",
        lambda: AgentResponse(is_complete=True, thought="done", summary="ok"),
    )

    result = agent.run_task(
        "Refine acceptance criteria",
        preserve_state=True,
        continuation_note="Tighten validation rules",
    )

    assert result.is_complete is True
    assert agent.session.state.goal == "Original task goal"
    assert agent.session.state.plan == ["step 1", "step 2"]
    assert agent.working_memory.goal == "Original task goal"

    last_user_message = [m for m in agent.session.messages if m.role == "user"][-1].content
    assert "Resume task goal: Original task goal" in last_user_message
    assert "Continuation update: Tighten validation rules" in last_user_message

    labels = [cp["label"] for cp in agent.list_checkpoints()]
    assert "task_start" in labels
    assert "task_complete" in labels
