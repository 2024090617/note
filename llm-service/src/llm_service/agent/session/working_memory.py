"""Working memory — bounded, task-scoped scratch-pad for the agent.

Maps to the Baddeley & Hitch (1974) working memory model:

* **Phonological loop** → ``notes``: keyed text entries (facts, sub-goals,
  intermediate reasoning) actively managed by the agent.
* **Visuospatial sketchpad** → ``artifacts``: structured data slots (code
  snippets, schemas, extracted tables) that need separate storage from
  free-text notes.
* **Central executive** → capacity enforcement.  When the buffer is full the
  oldest / lowest-priority items are evicted automatically.
* **Episodic buffer** → ``render()`` merges everything into a coherent
  ``<working_memory>`` XML block injected into the system prompt each turn.

Usage::

    from llm_service.agent.session.working_memory import WorkingMemory

    wm = WorkingMemory(max_items=20, max_tokens=2000)
    wm.set_goal("Fix auth timeout")
    wm.add_note("root-cause", "Token refresh window too short", priority=2)
    wm.add_artifact("config", "retry_backoff: 5s", label="current config")
    print(wm.render())    # → <working_memory>…</working_memory>
    wm.clear()            # task boundary → wipe everything
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# ── Item types ───────────────────────────────────────────────────────

@dataclass
class WMNote:
    """A keyed text entry in the phonological loop."""
    key: str
    content: str
    priority: int = 1          # higher = more important (kept longer)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def tokens(self) -> int:
        return _est_tokens(self.content)


@dataclass
class WMArtifact:
    """A structured data slot in the visuospatial sketchpad."""
    key: str
    data: str                  # code snippet, JSON, table, etc.
    label: str = ""            # human-readable short description
    priority: int = 1
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def tokens(self) -> int:
        return _est_tokens(self.data) + _est_tokens(self.label)


# ── WorkingMemory ────────────────────────────────────────────────────

class WorkingMemory:
    """Bounded, task-scoped scratch-pad.

    Args:
        max_items: Hard cap on total entries (notes + artifacts).
        max_tokens: Soft token budget for the rendered block.  0 = unlimited.
    """

    def __init__(self, max_items: int = 30, max_tokens: int = 3000) -> None:
        self.max_items = max(1, max_items)
        self.max_tokens = max_tokens

        self._goal: Optional[str] = None
        self._constraints: List[str] = []
        self._notes: OrderedDict[str, WMNote] = OrderedDict()
        self._artifacts: OrderedDict[str, WMArtifact] = OrderedDict()

    # ── Goal / constraints ───────────────────────────────────────────

    def set_goal(self, goal: str) -> None:
        self._goal = goal.strip() or None

    @property
    def goal(self) -> Optional[str]:
        return self._goal

    def add_constraint(self, text: str) -> None:
        text = text.strip()
        if text and text not in self._constraints:
            self._constraints.append(text)

    def clear_constraints(self) -> None:
        self._constraints.clear()

    # ── Phonological loop (notes) ────────────────────────────────────

    def add_note(self, key: str, content: str, priority: int = 1) -> None:
        """Add or update a keyed note.  Evicts if capacity exceeded."""
        key = key.strip().lower()
        if not key:
            raise ValueError("Note key must not be empty")
        self._notes[key] = WMNote(key=key, content=content.strip(), priority=priority)
        self._notes.move_to_end(key)  # most recent last
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

    # ── Visuospatial sketchpad (artifacts) ───────────────────────────

    def add_artifact(self, key: str, data: str, label: str = "", priority: int = 1) -> None:
        """Add or update a structured artifact.  Evicts if capacity exceeded."""
        key = key.strip().lower()
        if not key:
            raise ValueError("Artifact key must not be empty")
        self._artifacts[key] = WMArtifact(
            key=key, data=data.strip(), label=label.strip(), priority=priority,
        )
        self._artifacts.move_to_end(key)
        self._enforce_capacity()

    def remove_artifact(self, key: str) -> bool:
        key = key.strip().lower()
        if key in self._artifacts:
            del self._artifacts[key]
            return True
        return False

    def get_artifact(self, key: str) -> Optional[WMArtifact]:
        return self._artifacts.get(key.strip().lower())

    def list_artifacts(self) -> List[WMArtifact]:
        return list(self._artifacts.values())

    # ── Capacity management (central executive) ──────────────────────

    @property
    def item_count(self) -> int:
        return len(self._notes) + len(self._artifacts)

    @property
    def total_tokens(self) -> int:
        t = 0
        if self._goal:
            t += _est_tokens(self._goal)
        for c in self._constraints:
            t += _est_tokens(c)
        for n in self._notes.values():
            t += n.tokens
        for a in self._artifacts.values():
            t += a.tokens
        return t

    def _enforce_capacity(self) -> None:
        """Evict lowest-priority, oldest items until within limits."""
        while self.item_count > self.max_items:
            self._evict_one()
        if self.max_tokens > 0:
            while self.total_tokens > self.max_tokens and self.item_count > 0:
                self._evict_one()

    def _evict_one(self) -> None:
        """Remove the single lowest-priority, oldest item."""
        # Collect all items with their container
        candidates: List[tuple] = []
        for key, note in self._notes.items():
            candidates.append((note.priority, note.created_at, "note", key))
        for key, art in self._artifacts.items():
            candidates.append((art.priority, art.created_at, "artifact", key))

        if not candidates:
            return

        # Sort: lowest priority first, then oldest first
        candidates.sort(key=lambda c: (c[0], c[1]))
        _, _, kind, key = candidates[0]

        if kind == "note":
            del self._notes[key]
        else:
            del self._artifacts[key]
        logger.debug("Working memory evicted %s:%s", kind, key)

    # ── Episodic buffer — render for prompt injection ────────────────

    def render(self, max_tokens: int = 0) -> str:
        """Render the working memory as an XML block for the system prompt.

        Args:
            max_tokens: Soft budget override (0 = use self.max_tokens).

        Returns:
            ``<working_memory>…</working_memory>`` string, or ``""`` if empty.
        """
        if not self._goal and not self._notes and not self._artifacts:
            return ""

        budget = max_tokens if max_tokens > 0 else (self.max_tokens if self.max_tokens > 0 else float("inf"))
        used = 0
        lines: List[str] = ["<working_memory>"]

        # Goal
        if self._goal:
            block = f"  <goal>{self._goal}</goal>"
            cost = _est_tokens(block)
            if used + cost <= budget:
                lines.append(block)
                used += cost

        # Constraints
        if self._constraints and used < budget:
            lines.append("  <constraints>")
            for c in self._constraints:
                entry = f"    <c>{c}</c>"
                cost = _est_tokens(entry)
                if used + cost > budget:
                    break
                lines.append(entry)
                used += cost
            lines.append("  </constraints>")

        # Notes (phonological loop)
        if self._notes and used < budget:
            lines.append("  <notes>")
            # Render highest-priority first
            sorted_notes = sorted(self._notes.values(), key=lambda n: -n.priority)
            for note in sorted_notes:
                entry = f'    <note key="{note.key}" priority="{note.priority}">{note.content}</note>'
                cost = _est_tokens(entry)
                if used + cost > budget:
                    lines.append(f"    <!-- {len(sorted_notes) - sorted_notes.index(note)} more notes omitted -->")
                    break
                lines.append(entry)
                used += cost
            lines.append("  </notes>")

        # Artifacts (visuospatial sketchpad)
        if self._artifacts and used < budget:
            lines.append("  <artifacts>")
            sorted_arts = sorted(self._artifacts.values(), key=lambda a: -a.priority)
            for art in sorted_arts:
                label_attr = f' label="{art.label}"' if art.label else ""
                entry = f'    <artifact key="{art.key}"{label_attr}>\n{art.data}\n    </artifact>'
                cost = _est_tokens(entry)
                if used + cost > budget:
                    lines.append(f"    <!-- {len(sorted_arts) - sorted_arts.index(art)} more artifacts omitted -->")
                    break
                lines.append(entry)
                used += cost
            lines.append("  </artifacts>")

        lines.append("</working_memory>")

        rendered = "\n".join(lines)
        # If only the wrapper tags remain (goal/notes/artifacts all empty or skipped)
        if rendered.strip() == "<working_memory>\n</working_memory>":
            return ""
        return rendered

    # ── Lifecycle ────────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear everything — call at task boundaries."""
        self._goal = None
        self._constraints.clear()
        self._notes.clear()
        self._artifacts.clear()

    def summary(self) -> str:
        """One-line diagnostic."""
        parts = []
        if self._goal:
            parts.append(f"goal={self._goal[:30]}")
        parts.append(f"notes={len(self._notes)}")
        parts.append(f"artifacts={len(self._artifacts)}")
        parts.append(f"tokens≈{self.total_tokens}")
        return f"WorkingMemory({', '.join(parts)})"

    def to_dict(self) -> Dict[str, Any]:
        """Serialise for session save."""
        return {
            "goal": self._goal,
            "constraints": list(self._constraints),
            "notes": [
                {"key": n.key, "content": n.content, "priority": n.priority}
                for n in self._notes.values()
            ],
            "artifacts": [
                {"key": a.key, "data": a.data, "label": a.label, "priority": a.priority}
                for a in self._artifacts.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], **kwargs) -> "WorkingMemory":
        """Deserialise."""
        wm = cls(**kwargs)
        if data.get("goal"):
            wm.set_goal(data["goal"])
        for c in data.get("constraints", []):
            wm.add_constraint(c)
        for n in data.get("notes", []):
            wm.add_note(n["key"], n["content"], n.get("priority", 1))
        for a in data.get("artifacts", []):
            wm.add_artifact(a["key"], a["data"], a.get("label", ""), a.get("priority", 1))
        return wm
