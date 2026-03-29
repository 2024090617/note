"""Shared test fixtures for digimate."""

import os
import pytest
from pathlib import Path


@pytest.fixture
def tmp_workdir(tmp_path):
    """Temporary working directory for tests."""
    old = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old)


@pytest.fixture
def sample_config():
    """Minimal AgentConfig for testing."""
    from digimate.core.config import AgentConfig
    return AgentConfig(workdir="/tmp/test-workspace")
