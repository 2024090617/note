"""Tests for LLM Service configuration."""

import os
from pathlib import Path
import pytest
from llm_service.config import Config


def test_config_from_env(monkeypatch):
    """Test loading config from environment."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token_123")
    
    config = Config.from_env()
    assert config.github_token == "test_token_123"


def test_config_validate_auth():
    """Test auth validation."""
    # With token
    config = Config(github_token="test_token")
    assert config.validate_auth() is True
    
    # Without token
    config = Config(github_token="")
    assert config.validate_auth() is False


def test_config_defaults():
    """Test default configuration values."""
    config = Config(github_token="test")
    
    assert config.model == "gpt-4"
    assert config.max_tokens == 4096
    assert config.temperature == 0.7
    assert config.timeout == 60
    assert config.stream is False


def test_config_get_config_dir():
    """Test config directory creation."""
    config = Config(github_token="test")
    config_dir = config.get_config_dir()
    
    assert config_dir.exists()
    assert config_dir.is_dir()
    assert config_dir.name == ".llm-service"
