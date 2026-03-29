"""Simplified flat KV working memory — task-scoped scratch-pad."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class WMNote:
    key: str
    content: str
    priority: int = 1
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def tokens(self) -> int:
        return _est_tokens(self.content)


class WorkingMemory:
    """Bounded, task-scoped scratch-pad.

    Notes are keyed text entries. Capacity is enforced by item count
    and a soft token budget.  Lowest-priority / oldest items are evicted
    when limits are exceeded.
    """

    def __init__(self, max_items: int = 30, max_tokens: int = 3000) -> None:
        self.max_items = max(1, max_items)
        self.max_tokens = max_tokens
        self._goal: Optional[str] = None
        self._notes: OrderedDict[str, WMNote] = OrderedDict()

    # ── Goal ─────────────────────────────────────────────────────────

    def set_goal(self, goal: str) -> None:
        self._goal = goal.strip() or None

    @property
    def goal(self) -> Optional[str]:
        return self._goal

    # ── Notes ────────────────────────────────────────────────────────

    def add_note(self, key: str, content: str, priority: int = 1) -> None:
        key = key.strip().lower()
        if not key:
            raise ValueError("Note key must not be empty")
        self._notes[key] = WMNote(key=key, content=content.strip(), priority=priority)
        self._notes.move_to_end(key)
        self._enforce_capacity()

    def remove_note(self, key: str) -> bool:
        key = key.strip().lower()
        if key in self._notes:
            del self._notes[key]
            return True
        return False

    def get_note(self, key: str) -> Optional[WMNote]:
        return self._notes.get(key.strip().lower())

    def list_notes(self) -> List[WMNote]:
        return list(self._notes.values())

    # ── Capacity ─────────────────────────────────────────────────────

    @property
    def item_count(self) -> int:
        return len(self._notes)

    @property
    def total_tokens(self) -> int:
        t = _est_tokens(self._goal) if self._goal else 0
        for n in self._notes.values():
            t += n.tokens
        return t

    def _enforce_capacity(self) -> None:
        while self.item_count > self.max_items:
            self._evict_one()
        if self.max_tokens > 0:
            while self.total_tokens > self.max_tokens and self.item_count > 0:
                self._evict_one()

    def _evict_one(self) -> None:
        if not self._notes:
            return
        candidates = sorted(
            self._notes.values(), key=lambda n: (n.priority, n.created_at)
        )
        del self._notes[candidates[0].key]

    # ── Render for prompt injection ──────────────────────────────────

    def render(self, max_tokens: int = 0) -> str:
        if not self._goal and not self._notes:
            return ""

        budget = max_tokens if max_tokens > 0 else (self.max_tokens or float("inf"))
        used = 0
        lines: List[str] = ["<working_memory>"]

        if self._goal:
            block = f"  <goal>{self._goal}</goal>"
            cost = _est_tokens(block)
            if used + cost <= budget:
                lines.append(block)
                used += cost

        if self._notes and used < budget:
            lines.append("  <notes>")
            for note in sorted(self._notes.values(), key=lambda n: -n.priority):
                entry = f'    <note key="{note.key}" p="{note.priority}">{note.content}</note>'
                cost = _est_tokens(entry)
                if used + cost > budget:
                    break
                lines.append(entry)
                used += cost
            lines.append("  </notes>")

        lines.append("</working_memory>")
        rendered = "\n".join(lines)

        if rendered.strip() in ("<working_memory>\n</working_memory>", "<working_memory></working_memory>"):
            return ""
        return rendered

    # ── Lifecycle ────────────────────────────────────────────────────

    def clear(self) -> None:
        self._goal = None
        self._notes.clear()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self._goal,
            "notes": [
                {"key": n.key, "content": n.content, "priority": n.priority}
                for n in self._notes.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], **kwargs: Any) -> WorkingMemory:
        wm = cls(**kwargs)
        if data.get("goal"):
            wm.set_goal(data["goal"])
        for n in data.get("notes", []):
            wm.add_note(n["key"], n["content"], n.get("priority", 1))
        return wm
