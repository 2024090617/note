"""
Session management for the Agent.

Handles conversation history, state persistence, and action logging.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


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


@dataclass
class SessionState:
    """Current state of an agent session."""
    goal: Optional[str] = None
    constraints: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    plan: List[str] = field(default_factory=list)
    plan_step: int = 0
    files_read: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    commands_run: List[str] = field(default_factory=list)
    last_test_result: Optional[str] = None
    last_lint_result: Optional[str] = None
    git_branch: Optional[str] = None
    git_dirty: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        return cls(**data)
    
    def summary(self) -> str:
        """Get a brief summary of current state."""
        parts = []
        if self.goal:
            parts.append(f"Goal: {self.goal[:50]}...")
        if self.plan:
            parts.append(f"Plan: step {self.plan_step + 1}/{len(self.plan)}")
        if self.files_modified:
            parts.append(f"Modified: {len(self.files_modified)} files")
        if self.commands_run:
            parts.append(f"Commands: {len(self.commands_run)} run")
        return " | ".join(parts) if parts else "No active task"


@dataclass
class Session:
    """
    Agent session containing conversation history, state, and action log.
    
    Supports save/load for persistence.
    """
    id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    mode: str = "copilot"  # "copilot" or "github-models"
    model: str = "gpt-4o-mini"
    workdir: str = field(default_factory=lambda: str(Path.cwd()))
    system_prompt: Optional[str] = None
    messages: List[Message] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    state: SessionState = field(default_factory=SessionState)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def add_message(self, role: str, content: str) -> Message:
        """Add a message to the conversation."""
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        self.updated_at = datetime.now().isoformat()
        return msg
    
    def add_action(
        self,
        action_type: ActionType,
        description: str,
        target: Optional[str] = None,
        result: Optional[str] = None,
        success: bool = True,
    ) -> Action:
        """Log an action."""
        action = Action(
            type=action_type,
            description=description,
            target=target,
            result=result,
            success=success,
        )
        self.actions.append(action)
        self.updated_at = datetime.now().isoformat()
        return action
    
    def get_conversation_for_llm(self) -> List[Dict[str, str]]:
        """Get conversation history formatted for LLM API."""
        result = []
        if self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        
        for msg in self.messages:
            result.append({"role": msg.role, "content": msg.content})
        
        return result
    
    def clear_conversation(self):
        """Clear conversation history but keep state."""
        self.messages = []
        self.updated_at = datetime.now().isoformat()
    
    def set_goal(self, goal: str):
        """Set the current task goal."""
        self.state.goal = goal
        self.state.plan = []
        self.state.plan_step = 0
        self.state.decisions = []
        self.state.open_questions = []
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary."""
        return {
            "id": self.id,
            "mode": self.mode,
            "model": self.model,
            "workdir": self.workdir,
            "system_prompt": self.system_prompt,
            "messages": [m.to_dict() for m in self.messages],
            "actions": [a.to_dict() for a in self.actions],
            "state": self.state.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """Deserialize session from dictionary."""
        return cls(
            id=data.get("id", datetime.now().strftime("%Y%m%d_%H%M%S")),
            mode=data.get("mode", "copilot"),
            model=data.get("model", "gpt-4o-mini"),
            workdir=data.get("workdir", str(Path.cwd())),
            system_prompt=data.get("system_prompt"),
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            actions=[Action.from_dict(a) for a in data.get("actions", [])],
            state=SessionState.from_dict(data.get("state", {})),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )
    
    def save(self, path: str | Path):
        """Save session to JSON file."""
        path = Path(path)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, path: str | Path) -> "Session":
        """Load session from JSON file."""
        path = Path(path)
        with open(path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    def status_line(self) -> str:
        """Get a concise status line for display."""
        parts = [
            f"[{self.mode}]",
            f"model:{self.model}",
            f"dir:{Path(self.workdir).name}",
        ]
        if self.state.git_branch:
            dirty = "*" if self.state.git_dirty else ""
            parts.append(f"git:{self.state.git_branch}{dirty}")
        return " | ".join(parts)
