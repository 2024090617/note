"""Agent configuration and response types."""

from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List


class AgentMode(str, Enum):
    """Agent operating mode."""

    COPILOT = "copilot"
    GITHUB_MODELS = "github-models"


@dataclass
class AgentConfig:
    """Configuration for the agent."""

    mode: AgentMode = AgentMode.COPILOT
    model: str = "claude-haiku-4.5"
    workdir: str = field(default_factory=lambda: str(Path.cwd()))
    system_prompt: Optional[str] = None
    copilot_host: str = "127.0.0.1"
    copilot_port: int = 19823
    max_iterations: int = 20
    auto_confirm: bool = False  # Auto-confirm destructive actions
    verbose: bool = False
    log_dir: Optional[str] = None  # Directory for log files (defaults to ./agent_logs)
    log_to_file: bool = True  # Enable file logging to capture all interactions
    log_to_console: bool = False  # Console logging via stderr (separate from rich output)

    # Docker sandbox settings
    sandbox_enabled: bool = False  # Enable Docker sandbox for script execution
    sandbox_default_image: str = "python:3.12-slim"  # Default Docker image

    # MCP settings
    mcp_config_path: Optional[str] = None  # Path to mcp.json config file

    # Memory settings
    memory_strategy: str = "claude-code"  # "claude-code" | "openclaw" | "none"
    memory_dir: Optional[str] = None  # Defaults to <workdir>/.agent/memory

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

    # LLM-native orchestration settings
    intent_router: str = "llm"  # "llm" | "heuristic"
    intent_confidence_threshold: float = 0.6
    focus_mode_default: str = "free-chat"  # "strict-task" | "task-with-side-questions" | "free-chat"

    # Memory and large-content handling
    short_memory_update_interval: int = 3
    max_tool_output_chars: int = 12_000
    large_output_head_chars: int = 3_500
    large_output_tail_chars: int = 1_500

    # Chunked content pipeline settings
    enable_chunking: bool = True  # Enable chunked output adapter
    chunking_threshold_chars: int = 6_000  # Don't chunk unless output exceeds this
    chunking_strategy: str = "hybrid"  # "hybrid" | "paragraph" | "code-block" | "line"
    chunk_min_chars: int = 500
    chunk_max_chars: int = 4_000
    max_artifacts: int = 1_000  # Max artifacts kept in store

    # Web tool settings
    web_request_timeout: int = 20
    web_max_read_bytes: int = 2 * 1024 * 1024
    web_max_read_chars: int = 20_000
    web_max_download_bytes: int = 50 * 1024 * 1024
    web_block_private_hosts: bool = True

    # Chat planner policy settings
    chat_planner_allowed_tools: List[str] = field(default_factory=lambda: ["read_online_content"])
    chat_planner_max_tool_calls_per_turn: int = 1

    # Phase 3 retrieval reranking settings
    retrieval_candidate_multiplier: int = 3
    retrieval_weight_relevance: float = 0.6
    retrieval_weight_recency: float = 0.25
    retrieval_weight_task_alignment: float = 0.15
    enable_short_memory_promotion: bool = True

    # Phase 4 interruption lane settings
    side_lane_max_turns: int = 3
    side_lane_ttl_minutes: int = 20

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentConfig":
        mode = data.get("mode", "copilot")
        if isinstance(mode, str):
            mode = AgentMode(mode)
        return cls(
            mode=mode,
            model=data.get("model", "claude-haiku-4.5"),
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
            intent_router=data.get("intent_router", "llm"),
            intent_confidence_threshold=data.get("intent_confidence_threshold", 0.6),
            focus_mode_default=data.get("focus_mode_default", "free-chat"),
            short_memory_update_interval=max(1, int(data.get("short_memory_update_interval", 3))),
            max_tool_output_chars=max(2_000, int(data.get("max_tool_output_chars", 12_000))),
            large_output_head_chars=max(500, int(data.get("large_output_head_chars", 3_500))),
            large_output_tail_chars=max(300, int(data.get("large_output_tail_chars", 1_500))),
            enable_chunking=data.get("enable_chunking", True),
            chunking_threshold_chars=max(2_000, int(data.get("chunking_threshold_chars", 6_000))),
            chunking_strategy=data.get("chunking_strategy", "hybrid"),
            chunk_min_chars=max(200, int(data.get("chunk_min_chars", 500))),
            chunk_max_chars=max(1_000, int(data.get("chunk_max_chars", 4_000))),
            max_artifacts=max(100, int(data.get("max_artifacts", 1_000))),
            web_request_timeout=max(1, int(data.get("web_request_timeout", 20))),
            web_max_read_bytes=max(1_024, int(data.get("web_max_read_bytes", 2 * 1024 * 1024))),
            web_max_read_chars=max(500, int(data.get("web_max_read_chars", 20_000))),
            web_max_download_bytes=max(1_024, int(data.get("web_max_download_bytes", 50 * 1024 * 1024))),
            web_block_private_hosts=bool(data.get("web_block_private_hosts", True)),
            chat_planner_allowed_tools=[
                str(item).strip()
                for item in data.get("chat_planner_allowed_tools", ["read_online_content"])
                if str(item).strip()
            ]
            or ["read_online_content"],
            chat_planner_max_tool_calls_per_turn=max(
                0,
                int(data.get("chat_planner_max_tool_calls_per_turn", 1)),
            ),
            retrieval_candidate_multiplier=max(1, int(data.get("retrieval_candidate_multiplier", 3))),
            retrieval_weight_relevance=float(data.get("retrieval_weight_relevance", 0.6)),
            retrieval_weight_recency=float(data.get("retrieval_weight_recency", 0.25)),
            retrieval_weight_task_alignment=float(data.get("retrieval_weight_task_alignment", 0.15)),
            enable_short_memory_promotion=bool(data.get("enable_short_memory_promotion", True)),
            side_lane_max_turns=max(1, int(data.get("side_lane_max_turns", 3))),
            side_lane_ttl_minutes=max(1, int(data.get("side_lane_ttl_minutes", 20))),
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
