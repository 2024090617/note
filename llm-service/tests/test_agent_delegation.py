"""Tests for agent delegation engine."""

from llm_service.agent.core.config import AgentConfig
from llm_service.agent.core.delegation import DelegationEngine


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeClient:
    def __init__(self):
        self.calls = []

    def chat(self, messages, model=None):
        self.calls.append({"messages": messages, "model": model})
        system_prompt = messages[0].content.lower() if messages else ""
        if "lead engineer synthesizing" in system_prompt:
            return _FakeResponse("Synthesized recommendation")
        return _FakeResponse("Specialist review output")


def test_agent_config_delegation_defaults_from_dict():
    """Delegation config fields are loaded from dict."""
    config = AgentConfig.from_dict(
        {
            "enable_delegation": True,
            "max_specialists": 2,
            "max_candidate_pages": 4,
            "max_collab_rounds": 1,
        }
    )

    assert config.enable_delegation is True
    assert config.max_specialists == 2
    assert config.max_candidate_pages == 4
    assert config.max_collab_rounds == 1


def test_delegation_engine_reviews_and_synthesizes():
    """Delegation engine returns specialist and synthesis output."""
    client = _FakeClient()
    engine = DelegationEngine(client=client, model="gpt-4o-mini", max_specialists=2)

    result = engine.review_candidates(
        task="Fix login timeout issue",
        candidates=[
            {
                "title": "Auth timeout guide",
                "content": "Increase token refresh window and update retry backoff.",
                "owner": "Platform Team",
                "url": "https://confluence.local/auth-timeout",
                "last_updated": "2026-02-01",
            },
            {
                "title": "Legacy auth notes",
                "content": "Old notes for auth flow.",
                "owner": "Legacy Team",
                "url": "https://confluence.local/legacy-auth",
                "last_updated": "2023-01-01",
            },
        ],
        focus=["relevance", "freshness"],
    )

    assert result["success"] is True
    assert result["synthesis"] == "Synthesized recommendation"
    assert len(result["specialists"]) == 2
    assert len(client.calls) == 3


def test_delegation_engine_rejects_empty_candidates():
    """Delegation engine fails for missing candidates."""
    client = _FakeClient()
    engine = DelegationEngine(client=client, model="gpt-4o-mini")

    result = engine.review_candidates(task="Any task", candidates=[])

    assert result["success"] is False
    assert "No valid candidates" in result["error"]
