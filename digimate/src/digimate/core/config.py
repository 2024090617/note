"""Agent configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class AgentConfig:
    """All configuration for a digimate agent instance."""

    # ── LLM backend ──────────────────────────────────────────────────
    backend: str = "copilot"  # "copilot" | "openai"
    model: str = "gpt-4.1"
    api_base: Optional[str] = None  # For openai backend
    api_key: Optional[str] = None   # For openai backend
    copilot_host: str = "127.0.0.1"
    copilot_port: int = 19823
    request_timeout: int = 120  # seconds

    # ── Workspace ────────────────────────────────────────────────────
    workdir: str = field(default_factory=lambda: str(Path.cwd()))

    # ── Agent behaviour ──────────────────────────────────────────────
    max_iterations: int = 20
    max_chat_iterations: int = 6
    auto_confirm: bool = False
    verbose: bool = False

    # ── Context budget ───────────────────────────────────────────────
    context_window: int = 128_000
    response_reserve: int = 4_096
    auto_compact: bool = True

    # ── Memory ───────────────────────────────────────────────────────
    memory_strategy: str = "claude-code"  # "claude-code" | "none"
    memory_dir: Optional[str] = None      # default: <workdir>/.digimate/memory

    # ── MCP ──────────────────────────────────────────────────────────
    mcp_config_path: Optional[str] = None

    # ── Docker sandbox ───────────────────────────────────────────────
    sandbox_enabled: bool = False
    sandbox_default_image: str = "python:3.12-slim"

    # ── Tracer (process-flow log) ────────────────────────────────────
    trace_stderr: bool = True
    trace_file: bool = True
    trace_dir: str = ".digimate/log"

    # ── Large-content guard ──────────────────────────────────────────
    max_observation_tokens: int = 12_000      # Layer 1 universal guard
    read_file_auto_limit: int = 500           # auto-cap lines if no end_line
    web_preview_lines: int = 200              # preview lines for fetched pages
    command_output_limit: int = 50_000        # terminal stdout char cap
    overflow_dir: str = ".digimate/cache/overflow"

    # ── System prompt override ───────────────────────────────────────
    system_prompt: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentConfig:
        """Create config from a dict (e.g. JSON / TOML config file)."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    @classmethod
    def from_env(cls) -> AgentConfig:
        """Create config from DIGIMATE_* environment variables.

        Only fields with a non-empty env var are overridden; everything
        else keeps the dataclass default.
        """
        _ENV_MAP: Dict[str, tuple[str, type]] = {
            "DIGIMATE_BACKEND":         ("backend",          str),
            "DIGIMATE_MODEL":           ("model",            str),
            "DIGIMATE_API_BASE":        ("api_base",         str),
            "DIGIMATE_API_KEY":         ("api_key",          str),
            "DIGIMATE_WORKDIR":         ("workdir",          str),
            "DIGIMATE_MAX_ITERATIONS":  ("max_iterations",   int),
            "DIGIMATE_CONTEXT_WINDOW":  ("context_window",   int),
            "DIGIMATE_MCP_CONFIG":      ("mcp_config_path",  str),
            "DIGIMATE_MEMORY_STRATEGY": ("memory_strategy",  str),
            "DIGIMATE_MEMORY_DIR":      ("memory_dir",       str),
            "DIGIMATE_REQUEST_TIMEOUT": ("request_timeout",  int),
            "DIGIMATE_TRACE_STDERR":    ("trace_stderr",     bool),
            "DIGIMATE_TRACE_FILE":      ("trace_file",       bool),
            "DIGIMATE_AUTO_COMPACT":    ("auto_compact",     bool),
            "DIGIMATE_VERBOSE":         ("verbose",          bool),
        }
        data: Dict[str, Any] = {}
        for env_key, (field_name, cast) in _ENV_MAP.items():
            raw = os.environ.get(env_key, "").strip()
            if not raw:
                continue
            if cast is bool:
                data[field_name] = raw.lower() in ("1", "true", "yes")
            elif cast is int:
                data[field_name] = int(raw)
            else:
                data[field_name] = raw
        return cls.from_dict(data)
