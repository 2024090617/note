"""Tests for Phase 5: observability surfaces and stress-oriented chunking behavior."""

from llm_service.agent.core import Agent, AgentConfig, AgentMode
from llm_service.agent.tools.types import ToolResult


def _make_agent(tmp_path, max_artifacts=20):
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
        max_artifacts=max_artifacts,
        enable_chunking=True,
        chunking_threshold_chars=500,
        chunk_min_chars=200,
        chunk_max_chars=800,
        chunking_strategy="line",
    )
    return Agent(config)


def test_status_exposes_observability_fields(tmp_path):
    agent = _make_agent(tmp_path)

    status = agent.status()

    assert "chunking" in status
    assert status["chunking"]["enabled"] is True
    assert status["chunking"]["threshold_chars"] == 500
    assert status["chunking"]["strategy"] == "line"

    assert "artifact_store" in status
    assert status["artifact_store"]["artifact_count"] == 0
    assert status["artifact_store"]["max_artifacts"] == 20

    # No active run_task interaction yet, so interaction should be absent.
    assert "interaction" in status
    assert status["interaction"] is None


def test_chunking_stress_respects_artifact_capacity(tmp_path):
    agent = _make_agent(tmp_path, max_artifacts=7)
    assert agent.chunked_output_adapter is not None

    for i in range(30):
        payload = (f"line-{i}\n" * 300) + ("X" * (i + 50))
        result = ToolResult(success=True, output=payload)
        chunked = agent.chunked_output_adapter.process_tool_result(
            result,
            source_type="command_output",
            source_metadata={"command": f"fake-cmd-{i}"},
        )
        assert chunked.is_chunked is True
        assert chunked.artifact_id

    stats = agent.artifact_store.stats()
    assert stats["artifact_count"] <= 7
    assert stats["max_artifacts"] == 7

    status = agent.status()
    assert status["artifact_store"]["artifact_count"] <= 7
