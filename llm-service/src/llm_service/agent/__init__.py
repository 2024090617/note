"""
LLM Agent - Autonomous software developer agent using Copilot Bridge.

This module provides an intelligent agent that can:
- Read requirements from documents
- Create and modify files
- Inspect development environments
- Run tests and fix issues
- Work autonomously following a ReAct (Reason + Act) loop
"""

from .core import Agent, AgentConfig
from .copilot_client import CopilotBridgeClient
from .session import Session, SessionState
from .tools import ToolRegistry
from .logger import AgentLogger, LogLevel, get_logger, set_logger

__all__ = [
    "Agent",
    "AgentConfig", 
    "CopilotBridgeClient",
    "Session",
    "SessionState",
    "ToolRegistry",
    "AgentLogger",
    "LogLevel",
    "get_logger",
    "set_logger",
]
