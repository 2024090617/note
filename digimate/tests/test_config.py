"""Tests for core/config.py."""

from digimate.core.config import AgentConfig


def test_default_config():
    cfg = AgentConfig()
    assert cfg.backend == "copilot"
    assert cfg.model == "gpt-4.1"
    assert cfg.max_iterations == 20
    assert cfg.context_window == 128_000


def test_from_dict():
    cfg = AgentConfig.from_dict({"backend": "openai", "model": "llama3", "unknown_field": 123})
    assert cfg.backend == "openai"
    assert cfg.model == "llama3"


def test_from_dict_ignores_unknown():
    cfg = AgentConfig.from_dict({"foo": "bar"})
    assert cfg.backend == "copilot"
