"""Action and message types for the session."""

from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


class ActionType(str, Enum):
    """Types of actions the agent can perform."""

    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_CREATE = "file_create"
    FILE_DELETE = "file_delete"
    COMMAND_RUN = "command_run"
    SEARCH = "search"
    LLM_CALL = "llm_call"
    PLAN = "plan"
    VERIFY = "verify"


@dataclass
class Action:
    """Record of an action taken by the agent."""

    type: ActionType
    description: str
    target: Optional[str] = None  # file path, command, etc.
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
    def from_dict(cls, data: Dict[str, Any]) -> "Action":
        return cls(
            type=ActionType(data["type"]),
            description=data["description"],
            target=data.get("target"),
            result=data.get("result"),
            success=data.get("success", True),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


@dataclass
class Message:
    """Conversation message."""

    role: str  # "system", "user", "assistant"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
