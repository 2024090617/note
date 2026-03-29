"""Linear conversation session with compaction support."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from digimate.core.types import Action, ActionType, Message
from digimate.session.budget import estimate_tokens

_COMPACT_KEEP_RECENT = 4


@dataclass
class Session:
    """Linear conversation history with persistence and compaction."""

    id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    model: str = "gpt-4o"
    workdir: str = field(default_factory=lambda: str(Path.cwd()))
    system_prompt: Optional[str] = None
    messages: List[Message] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    _compaction_count: int = field(default=0, init=False, repr=False)

    # ── Messages ─────────────────────────────────────────────────────

    def add_message(self, role: str, content: str) -> Message:
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        self.updated_at = datetime.now().isoformat()
        return msg

    def get_messages(self, limit: Optional[int] = None) -> List[Message]:
        if limit is not None:
            return self.messages[-limit:]
        return list(self.messages)

    def get_conversation_for_llm(self) -> List[Dict[str, str]]:
        result: List[Dict[str, str]] = []
        if self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        for msg in self.messages:
            result.append({"role": msg.role, "content": msg.content})
        return result

    # ── Actions ──────────────────────────────────────────────────────

    def add_action(
        self,
        action_type: ActionType,
        description: str,
        target: Optional[str] = None,
        result: Optional[str] = None,
        success: bool = True,
    ) -> Action:
        action = Action(
            type=action_type, description=description,
            target=target, result=result, success=success,
        )
        self.actions.append(action)
        self.updated_at = datetime.now().isoformat()
        return action

    # ── Token estimation ─────────────────────────────────────────────

    def estimate_history_tokens(self) -> int:
        return sum(estimate_tokens(m.content) for m in self.messages)

    # ── Compaction ───────────────────────────────────────────────────

    def compact(self, keep_recent: int = _COMPACT_KEEP_RECENT) -> str:
        """Summarise old messages, keeping the most recent ones intact.

        Returns the summary text, or "" if too few messages.
        """
        if len(self.messages) <= keep_recent + 2:
            return ""

        old = self.messages[:-keep_recent] if keep_recent > 0 else list(self.messages)

        lines = ["[Conversation summary — older turns compacted to save context]"]
        for msg in old:
            short = msg.content[:150].replace("\n", " ")
            if len(msg.content) > 150:
                short += "..."
            lines.append(f"  {msg.role.upper()}: {short}")

        summary_text = "\n".join(lines)
        summary_msg = Message(role="user", content=summary_text)

        old_ids = {m.id for m in old}
        self.messages = [m for m in self.messages if m.id not in old_ids]
        self.messages.insert(0, summary_msg)
        self._compaction_count += 1
        self.updated_at = datetime.now().isoformat()
        return summary_text

    # ── Persistence ──────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "id": self.id,
            "model": self.model,
            "workdir": self.workdir,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [m.to_dict() for m in self.messages],
            "actions": [a.to_dict() for a in self.actions],
        }
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Session:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            id=data.get("id", ""),
            model=data.get("model", ""),
            workdir=data.get("workdir", "."),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            actions=[Action.from_dict(a) for a in data.get("actions", [])],
        )

    def clear(self) -> None:
        self.messages.clear()
        self.updated_at = datetime.now().isoformat()
