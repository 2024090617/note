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
