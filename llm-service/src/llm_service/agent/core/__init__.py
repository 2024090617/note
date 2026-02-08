"""
Core Agent - ReAct-style autonomous developer agent.

Split into submodules for readability:
- config: AgentConfig, AgentMode, AgentResponse
- prompt: System prompt constant
- agent: Agent class
"""

from .config import AgentConfig, AgentMode, AgentResponse
from .prompt import DEVELOPER_AGENT_SYSTEM_PROMPT
from .agent import Agent

__all__ = [
    "Agent",
    "AgentConfig",
    "AgentMode",
    "AgentResponse",
    "DEVELOPER_AGENT_SYSTEM_PROMPT",
]
