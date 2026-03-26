"""Tests for Phase 3 retrieval reranking and memory promotion."""

from llm_service.agent.core import Agent, AgentConfig, AgentMode
from llm_service.agent.core.retrieval_reranker import RetrievalReranker


class _FakeMemoryManager:
    name = "claude-code"

    def __init__(self):
        self.items = []

    def store(self, content, topic=None):
        self.items.append((content, topic))
        return "ok"


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
        intent_router="llm",
    )
    return Agent(config)


def test_reranker_prefers_task_aligned_snippet():
    reranker = RetrievalReranker()
    snippets = [
        {
            "doc_id": "thread:t1|message:old|role:user",
            "content": "General chat about weather and travel plans.",
            "score": 0.95,
        },
        {
            "doc_id": "thread:t1|message:new|role:user",
            "content": "Retry logic for network timeout and exponential backoff.",
            "score": 0.70,
        },
    ]

    ranked = reranker.rerank_snippets(
        snippets=snippets,
        query="implement retry backoff",
        task_context="Fix HTTP timeout retries",
        message_recency_index={"old": 0.1, "new": 1.0},
        limit=2,
    )

    assert ranked[0]["doc_id"].endswith("message:new|role:user")


def test_agent_retrieved_context_block_includes_rerank_score(monkeypatch, tmp_path):
    agent = _make_agent(tmp_path)
    agent.session.set_task_anchor("Implement timeout retry", milestone="planning")
    agent.session.set_short_memory("Goal: Implement timeout retry", "Add tests")

    monkeypatch.setattr(
        agent.conversation_index,
        "search",
        lambda query, limit, thread_id=None: [
            {
                "doc_id": "thread:t1|message:m1|role:user",
                "content": "Need retry for timeout errors",
                "score": 0.8,
            }
        ],
    )

    block = agent._build_retrieved_context_block("retry timeout")

    assert "<retrieved_conversation" in block
    assert "score=\"" in block


def test_short_memory_promotion_runs_once_per_goal(tmp_path):
    agent = _make_agent(tmp_path)
    fake_memory = _FakeMemoryManager()
    agent.memory_manager = fake_memory

    agent.session.set_goal("Implement retries")
    agent._refresh_short_memory(milestone="Task completed")
    agent._refresh_short_memory(milestone="Task completed")

    assert len(fake_memory.items) == 1
    stored, topic = fake_memory.items[0]
    assert "Completed task: Implement retries" in stored
    assert topic == "task-outcomes"
