"""Session state management."""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional


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
