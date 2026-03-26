"""Agent configuration and response types."""

from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional


class AgentMode(str, Enum):
    """Agent operating mode."""

    COPILOT = "copilot"
    GITHUB_MODELS = "github-models"


@dataclass
class AgentConfig:
    """Configuration for the agent."""

    mode: AgentMode = AgentMode.COPILOT
    model: str = "gpt-4o-mini"
    workdir: str = field(default_factory=lambda: str(Path.cwd()))
    system_prompt: Optional[str] = None
    copilot_host: str = "127.0.0.1"
    copilot_port: int = 19823
    max_iterations: int = 20
    auto_confirm: bool = False  # Auto-confirm destructive actions
    verbose: bool = False
    log_dir: Optional[str] = None  # Directory for log files
    log_to_file: bool = True  # Enable file logging
    log_to_console: bool = False  # Enable console logging (separate from rich output)

    # Docker sandbox settings
    sandbox_enabled: bool = False  # Enable Docker sandbox for script execution
    sandbox_default_image: str = "python:3.12-slim"  # Default Docker image

    # MCP settings
    mcp_config_path: Optional[str] = None  # Path to mcp.json config file

    # Memory settings
    memory_strategy: str = "claude-code"  # "claude-code" | "openclaw" | "none"
    memory_dir: Optional[str] = None  # Defaults to <workdir>/.digimate/memory

    # Delegation settings
    enable_delegation: bool = False
    max_specialists: int = 3
    max_candidate_pages: int = 5
    max_collab_rounds: int = 1

    # Context budget settings
    context_window: int = 128_000   # model context window in tokens
    response_reserve: int = 4_096   # tokens reserved for LLM response
    auto_compact: bool = True       # auto-compact session when budget exceeded

    # Topic-isolated context settings
    context_recent_messages: int = 4
    context_retrieval_limit: int = 4
    topic_shift_threshold: float = 0.55

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentConfig":
        mode = data.get("mode", "copilot")
        if isinstance(mode, str):
            mode = AgentMode(mode)
        return cls(
            mode=mode,
            model=data.get("model", "gpt-4o-mini"),
            workdir=data.get("workdir", str(Path.cwd())),
            system_prompt=data.get("system_prompt"),
            copilot_host=data.get("copilot_host", "127.0.0.1"),
            copilot_port=data.get("copilot_port", 19823),
            max_iterations=data.get("max_iterations", 20),
            auto_confirm=data.get("auto_confirm", False),
            verbose=data.get("verbose", False),
            log_dir=data.get("log_dir"),
            log_to_file=data.get("log_to_file", True),
            log_to_console=data.get("log_to_console", False),
            sandbox_enabled=data.get("sandbox_enabled", False),
            sandbox_default_image=data.get("sandbox_default_image", "python:3.12-slim"),
            mcp_config_path=data.get("mcp_config_path"),
            memory_strategy=data.get("memory_strategy", "claude-code"),
            memory_dir=data.get("memory_dir"),
            enable_delegation=data.get("enable_delegation", False),
            max_specialists=data.get("max_specialists", 3),
            max_candidate_pages=data.get("max_candidate_pages", 5),
            max_collab_rounds=data.get("max_collab_rounds", 1),
            context_window=data.get("context_window", 128_000),
            response_reserve=data.get("response_reserve", 4_096),
            auto_compact=data.get("auto_compact", True),
            context_recent_messages=data.get("context_recent_messages", 4),
            context_retrieval_limit=data.get("context_retrieval_limit", 4),
            topic_shift_threshold=data.get("topic_shift_threshold", 0.55),
        )


@dataclass
class AgentResponse:
    """Response from agent execution."""

    thought: Optional[str] = None
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    action_result: Optional[str] = None
    is_complete: bool = False
    summary: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None
