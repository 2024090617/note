"""Core types shared across digimate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


# ── Chat / LLM messages ─────────────────────────────────────────────

@dataclass
class ChatMessage:
    """Message sent to / received from the LLM."""

    role: str  # "system", "user", "assistant"
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatResponse:
    """Parsed response from an LLM backend."""

    content: str
    model: str = ""
    finish_reason: str = "stop"


# ── Tool results ─────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """Return value from any tool execution."""

    success: bool
    output: str
    error: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    # Large-content guard fields (set by Layer 1 truncation)
    truncated: bool = False
    overflow_path: Optional[str] = None
    original_tokens: Optional[int] = None


# ── Agent response (parsed ReAct output) ─────────────────────────────

@dataclass
class AgentResponse:
    """Parsed response from one ReAct iteration."""

    thought: Optional[str] = None
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    action_result: Optional[str] = None
    is_complete: bool = False
    summary: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None


# ── Session message ──────────────────────────────────────────────────

@dataclass
class Message:
    """Conversation message stored in session history."""

    role: str  # "system", "user", "assistant"
    content: str
    id: str = field(default_factory=lambda: f"msg_{uuid4().hex[:12]}")
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Message:
        return cls(
            id=data.get("id", f"msg_{uuid4().hex[:12]}"),
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


# ── Action log entry ─────────────────────────────────────────────────

class ActionType(str, Enum):
    """Categories for logged actions."""

    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_CREATE = "file_create"
    FILE_DELETE = "file_delete"
    COMMAND_RUN = "command_run"
    SEARCH = "search"
    GIT = "git"
    WEB_FETCH = "web_fetch"
    MCP_CALL = "mcp_call"
    LLM_CALL = "llm_call"


@dataclass
class Action:
    """Record of an action taken by the agent."""

    type: ActionType
    description: str
    target: Optional[str] = None
    result: Optional[str] = None
    success: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "description": self.description,
            "target": self.target,
            "result": self.result,
            "success": self.success,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Action:
        return cls(
            type=ActionType(data["type"]),
            description=data["description"],
            target=data.get("target"),
            result=data.get("result"),
            success=data.get("success", True),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
