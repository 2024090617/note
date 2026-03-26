"""Session class for conversation history and state."""

import json
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from uuid import uuid4

from .types import Action, ActionType, Message
from .state import SessionState
from .budget import ContextBudgetManager, estimate_tokens

logger = logging.getLogger(__name__)

# When compacting, keep the most recent N message pairs intact
_COMPACT_KEEP_RECENT = 4


@dataclass
class Session:
    """
    Agent session containing conversation history, state, and action log.

    Supports save/load for persistence.
    Now includes context-budget awareness and automatic compaction.
    """

    id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    mode: str = "copilot"  # "copilot" or "github-models"
    model: str = "gpt-4o-mini"
    workdir: str = field(default_factory=lambda: str(Path.cwd()))
    system_prompt: Optional[str] = None
    messages: List[Message] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    state: SessionState = field(default_factory=SessionState)
    threads: List[Dict[str, Any]] = field(default_factory=list)
    current_thread_id: Optional[str] = None
    focus_thread_id: Optional[str] = None  # None = current thread only
    focus_mode: str = "free-chat"  # strict-task | task-with-side-questions | free-chat
    task_anchor: Dict[str, Any] = field(default_factory=dict)
    short_memory: Dict[str, Any] = field(default_factory=dict)
    side_lane: Dict[str, Any] = field(default_factory=dict)
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Compaction tracking
    _compaction_count: int = field(default=0, init=False, repr=False)

    def __post_init__(self):
        """Ensure thread metadata is initialized for backward compatibility."""
        if not self.threads:
            default = self.create_thread("general")
            self.current_thread_id = default["id"]
        elif not self.current_thread_id:
            self.current_thread_id = self.threads[0]["id"]

        for thread in self.threads:
            thread.setdefault("summary", "")
            thread.setdefault("summary_pinned", False)
            thread.setdefault("created_at", self.created_at)
            thread.setdefault("updated_at", self.updated_at)

    def add_message(self, role: str, content: str, thread_id: Optional[str] = None) -> Message:
        """Add a message to the conversation."""
        target_thread = thread_id or self.current_thread_id
        msg = Message(role=role, content=content, thread_id=target_thread)
        self.messages.append(msg)
        if target_thread:
            self.touch_thread(target_thread)
            # Keep a compact rolling summary to improve thread context selection.
            self.update_thread_summary(target_thread)
        self.updated_at = datetime.now().isoformat()
        return msg

    def create_thread(self, topic: str, switch: bool = True) -> Dict[str, Any]:
        """Create a new conversation thread."""
        thread = {
            "id": f"th_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}",
            "topic": topic.strip() or "general",
            "summary": "",
            "summary_pinned": False,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self.threads.append(thread)
        if switch:
            self.current_thread_id = thread["id"]
        self.updated_at = datetime.now().isoformat()
        return thread

    def touch_thread(self, thread_id: str) -> None:
        """Update thread activity timestamp."""
        for thread in self.threads:
            if thread["id"] == thread_id:
                thread["updated_at"] = datetime.now().isoformat()
                return

    def list_threads(self) -> List[Dict[str, Any]]:
        """Return threads ordered by most recently updated."""
        return sorted(self.threads, key=lambda t: t.get("updated_at", ""), reverse=True)

    def update_thread_summary(self, thread_id: str, max_messages: int = 8, force: bool = False) -> str:
        """Generate a compact summary for a thread from its recent messages."""
        thread = self.get_thread(thread_id)
        if thread is None:
            return ""
        if thread.get("summary_pinned") and not force:
            return str(thread.get("summary") or "")

        thread_messages = self.get_thread_messages(thread_id=thread_id, limit=max_messages)
        if not thread_messages:
            return ""

        lines: List[str] = []
        for msg in thread_messages:
            role = msg.role.upper()
            short = msg.content.replace("\n", " ").strip()
            if len(short) > 120:
                short = short[:120] + "..."
            lines.append(f"{role}: {short}")

        summary = " | ".join(lines)
        if len(summary) > 700:
            summary = summary[:700] + "..."

        thread["summary"] = summary
        thread["updated_at"] = datetime.now().isoformat()

        return summary

    def get_thread(self, identifier: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Resolve a thread by id, topic, or current when omitted."""
        target = identifier or self.current_thread_id
        if not target:
            return None

        for thread in self.threads:
            if thread.get("id") == target:
                return thread

        for thread in reversed(self.threads):
            if thread.get("topic") == target:
                return thread

        return None

    def set_thread_summary(
        self,
        summary: str,
        thread_id: Optional[str] = None,
        pinned: bool = True,
    ) -> bool:
        """Set a manual summary for a thread and optionally pin it."""
        thread = self.get_thread(thread_id)
        if not thread:
            return False

        thread["summary"] = summary.strip()
        thread["summary_pinned"] = bool(pinned)
        thread["updated_at"] = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
        return True

    def set_thread_summary_pinned(self, pinned: bool, thread_id: Optional[str] = None) -> bool:
        """Pin or unpin a thread summary."""
        thread = self.get_thread(thread_id)
        if not thread:
            return False
        thread["summary_pinned"] = bool(pinned)
        thread["updated_at"] = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
        return True

    def get_current_thread(self) -> Optional[Dict[str, Any]]:
        """Return the active conversation thread."""
        return self.get_thread(self.current_thread_id)

    def set_current_thread(self, identifier: str) -> bool:
        """Switch current thread by id or topic name."""
        for thread in self.threads:
            if thread["id"] == identifier:
                self.current_thread_id = thread["id"]
                self.updated_at = datetime.now().isoformat()
                return True

        for thread in reversed(self.threads):
            if thread["topic"] == identifier:
                self.current_thread_id = thread["id"]
                self.updated_at = datetime.now().isoformat()
                return True

        return False

    def set_focus(self, value: Optional[str]) -> None:
        """Configure retrieval focus: None=current, 'all'=cross-thread, or thread id."""
        if not value or value == "current":
            self.focus_thread_id = None
        elif value == "all":
            self.focus_thread_id = "all"
        else:
            self.focus_thread_id = value
        self.updated_at = datetime.now().isoformat()

    def set_focus_mode(self, mode: str) -> None:
        """Set attention mode used by the LLM-native orchestrator."""
        allowed = {"strict-task", "task-with-side-questions", "free-chat"}
        self.focus_mode = mode if mode in allowed else "free-chat"
        self.updated_at = datetime.now().isoformat()

    def set_task_anchor(
        self,
        objective: str,
        milestone: str = "",
        blockers: Optional[List[str]] = None,
    ) -> None:
        """Store compact task anchor metadata for focus and retrieval filtering."""
        self.task_anchor = {
            "objective": objective.strip(),
            "milestone": milestone.strip(),
            "blockers": list(blockers or []),
            "updated_at": datetime.now().isoformat(),
        }
        self.updated_at = datetime.now().isoformat()

    def set_short_memory(
        self,
        summary: str,
        next_action: str = "",
        blockers: Optional[List[str]] = None,
    ) -> None:
        """Store a compact rolling digest used as short-term memory."""
        self.short_memory = {
            "summary": summary.strip(),
            "next_action": next_action.strip(),
            "blockers": list(blockers or []),
            "updated_at": datetime.now().isoformat(),
        }
        self.updated_at = datetime.now().isoformat()

    def start_side_lane(self, prompt: str) -> None:
        """Start an ephemeral side-question lane while a task remains active."""
        now = datetime.now().isoformat()
        self.side_lane = {
            "active": True,
            "turns": 1,
            "started_at": now,
            "updated_at": now,
            "summary": prompt.strip()[:240],
            "history": [prompt.strip()[:240]],
        }
        self.updated_at = now

    def append_side_lane(self, content: str) -> None:
        """Append a user turn to the side-question lane."""
        if not self.side_lane.get("active"):
            self.start_side_lane(content)
            return

        history = list(self.side_lane.get("history", []))
        history.append(content.strip()[:240])
        self.side_lane["history"] = history[-8:]
        self.side_lane["turns"] = int(self.side_lane.get("turns", 0)) + 1
        self.side_lane["updated_at"] = datetime.now().isoformat()
        self.side_lane["summary"] = " | ".join(self.side_lane["history"][-3:])[:300]
        self.updated_at = datetime.now().isoformat()

    def clear_side_lane(self) -> None:
        """Clear ephemeral side-question lane state."""
        self.side_lane = {}
        self.updated_at = datetime.now().isoformat()

    def should_evict_side_lane(self, max_turns: int, ttl_minutes: int) -> bool:
        """Check if side lane should be evicted by turn count or age."""
        if not self.side_lane.get("active"):
            return False

        turns = int(self.side_lane.get("turns", 0))
        if turns >= max_turns:
            return True

        updated_at = str(self.side_lane.get("updated_at", ""))
        if not updated_at:
            return False

        try:
            age = datetime.now() - datetime.fromisoformat(updated_at)
        except Exception:
            return False
        return age.total_seconds() >= ttl_minutes * 60

    def get_thread_messages(
        self,
        thread_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Message]:
        """Get messages for a thread, defaulting to current thread."""
        tid = thread_id or self.current_thread_id
        filtered = [
            msg for msg in self.messages if (msg.thread_id == tid or (msg.thread_id is None and tid == self.current_thread_id))
        ]
        if limit is not None:
            return filtered[-limit:]
        return filtered

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

        for msg in self.get_thread_messages():
            result.append({"role": msg.role, "content": msg.content})

        return result

    # ------------------------------------------------------------------
    # Token estimation
    # ------------------------------------------------------------------

    def estimate_history_tokens(self) -> int:
        """Estimate total tokens in conversation messages."""
        return sum(estimate_tokens(m.content) for m in self.messages)

    # ------------------------------------------------------------------
    # Compaction
    # ------------------------------------------------------------------

    def compact(self, keep_recent: int = _COMPACT_KEEP_RECENT) -> str:
        """Summarise old messages into a single recap, keeping recent ones.

        Returns the summary text that replaced the old messages, or empty
        string if compaction was not needed (too few messages).
        """
        current_tid = self.current_thread_id
        thread_messages = self.get_thread_messages(thread_id=current_tid)

        # Need at least keep_recent + 2 messages to be worth compacting
        if len(thread_messages) <= keep_recent + 2:
            return ""

        old_messages = thread_messages[: -keep_recent] if keep_recent > 0 else thread_messages[:]
        recent_messages = thread_messages[-keep_recent:] if keep_recent > 0 else []

        # Build a compact summary of old messages
        summary_lines: List[str] = [
            "[Conversation summary — older turns compacted to save context]",
        ]

        # Group into turns and create condensed recap
        for msg in old_messages:
            role_tag = msg.role.upper()
            # Truncate long content to first 150 chars
            short = msg.content[:150].replace("\n", " ")
            if len(msg.content) > 150:
                short += "..."
            summary_lines.append(f"  {role_tag}: {short}")

        summary_text = "\n".join(summary_lines)

        # Replace old messages with one summary message
        summary_msg = Message(role="user", content=summary_text, thread_id=current_tid)
        old_ids = {m.id for m in old_messages}
        survivors = [m for m in self.messages if m.id not in old_ids]
        insert_at = 0
        for idx, msg in enumerate(survivors):
            if msg.thread_id == current_tid:
                insert_at = idx
                break
        survivors.insert(insert_at, summary_msg)
        self.messages = survivors
        self._compaction_count += 1
        self.updated_at = datetime.now().isoformat()

        logger.info(
            "Session compacted: %d old messages → summary (%d tokens), "
            "kept %d recent. Total compactions: %d",
            len(old_messages),
            estimate_tokens(summary_text),
            len(recent_messages),
            self._compaction_count,
        )
        return summary_text

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

    def create_checkpoint(
        self,
        label: str,
        working_memory: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Capture a checkpoint snapshot for task continuation."""
        checkpoint = {
            "id": f"cp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}",
            "label": label.strip() or "checkpoint",
            "created_at": datetime.now().isoformat(),
            "goal": self.state.goal,
            "state": self.state.to_dict(),
            "message_count": len(self.messages),
            "action_count": len(self.actions),
            "working_memory": working_memory,
            "metadata": metadata or {},
        }
        self.checkpoints.append(checkpoint)
        self.updated_at = datetime.now().isoformat()
        return checkpoint

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List all checkpoints in creation order."""
        return list(self.checkpoints)

    def get_checkpoint(self, identifier: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Resolve a checkpoint by id, label, or latest when omitted."""
        if not self.checkpoints:
            return None

        if not identifier:
            return self.checkpoints[-1]

        for checkpoint in self.checkpoints:
            if checkpoint.get("id") == identifier:
                return checkpoint

        # If a label is provided, return the latest checkpoint with that label.
        for checkpoint in reversed(self.checkpoints):
            if checkpoint.get("label") == identifier:
                return checkpoint

        return None

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
            "threads": list(self.threads),
            "current_thread_id": self.current_thread_id,
            "focus_thread_id": self.focus_thread_id,
            "focus_mode": self.focus_mode,
            "task_anchor": dict(self.task_anchor),
            "short_memory": dict(self.short_memory),
            "side_lane": dict(self.side_lane),
            "checkpoints": list(self.checkpoints),
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
            threads=list(data.get("threads", [])),
            current_thread_id=data.get("current_thread_id"),
            focus_thread_id=data.get("focus_thread_id"),
            focus_mode=data.get("focus_mode", "free-chat"),
            task_anchor=dict(data.get("task_anchor", {})),
            short_memory=dict(data.get("short_memory", {})),
            side_lane=dict(data.get("side_lane", {})),
            checkpoints=list(data.get("checkpoints", [])),
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
        current = self.get_current_thread()
        if current:
            parts.append(f"topic:{current['topic']}")
        if self.state.git_branch:
            dirty = "*" if self.state.git_dirty else ""
            parts.append(f"git:{self.state.git_branch}{dirty}")
        return " | ".join(parts)
