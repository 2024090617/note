"""Context budget manager for token-aware prompt construction.

Tracks token usage per component (system prompt, memory, skills, MCP tools,
conversation history, response reserve) and enforces a configurable budget
so the agent never exceeds the model's context window.

Token estimation uses a simple chars÷4 heuristic — accurate enough for
budget decisions without requiring a tokenizer dependency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────
DEFAULT_CONTEXT_WINDOW = 128_000  # GPT-4o / Claude Sonnet class
DEFAULT_RESPONSE_RESERVE = 4_096  # tokens reserved for LLM output

# Allocation ratios (fractions of *available* = window − reserve)
_DEFAULT_RATIOS: Dict[str, float] = {
    "system_prompt": 0.15,
    "memory": 0.10,
    "short_memory": 0.05,
    "working_memory": 0.05,
    "skills": 0.05,
    "mcp_tools": 0.05,
    "history": 0.55,  # bulk of the budget
}


def estimate_tokens(text: str) -> int:
    """Fast token estimate: ~4 chars per token for English/code."""
    return max(1, len(text) // 4)


# ── Budget Slot ──────────────────────────────────────────────────────
@dataclass
class _Slot:
    """Token allocation for one prompt component."""

    name: str
    ratio: float
    limit: int = 0       # absolute limit computed from ratio * available
    used: int = 0         # tokens currently consumed

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exceeded(self) -> bool:
        return self.used > self.limit


# ── ContextBudgetManager ─────────────────────────────────────────────
@dataclass
class ContextBudgetManager:
    """Manages token budget across prompt components.

    Usage::

        mgr = ContextBudgetManager(context_window=128_000)
        mgr.reset()

        # Register component text
        mgr.record("system_prompt", system_text)
        mgr.record("memory", memory_block)
        mgr.record("history", history_text)

        # Check budget
        if mgr.is_over_budget():
            ...  # trigger compaction

        # Remaining quota for history
        remaining = mgr.remaining("history")
    """

    context_window: int = DEFAULT_CONTEXT_WINDOW
    response_reserve: int = DEFAULT_RESPONSE_RESERVE
    ratios: Dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_RATIOS))

    # internal
    _slots: Dict[str, _Slot] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._recompute_limits()

    # ── public API ───────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset all used counters to zero (call at the start of each turn)."""
        for slot in self._slots.values():
            slot.used = 0

    def record(self, component: str, text: str) -> int:
        """Record token usage for *component*. Returns tokens consumed."""
        tokens = estimate_tokens(text)
        slot = self._slots.get(component)
        if slot is None:
            # Unknown component — create an unbounded slot
            slot = _Slot(name=component, ratio=0.0, limit=self.available)
            self._slots[component] = slot
        slot.used = tokens
        return tokens

    def remaining(self, component: str) -> int:
        """Remaining token budget for *component*."""
        slot = self._slots.get(component)
        if slot is None:
            return self.available
        return slot.remaining

    def limit(self, component: str) -> int:
        """Token limit for *component*."""
        slot = self._slots.get(component)
        if slot is None:
            return 0
        return slot.limit

    def is_over_budget(self) -> bool:
        """True if total used exceeds context_window − response_reserve."""
        return self.total_used > self.available

    @property
    def available(self) -> int:
        """Total tokens available (window − reserve)."""
        return max(0, self.context_window - self.response_reserve)

    @property
    def total_used(self) -> int:
        return sum(s.used for s in self._slots.values())

    @property
    def total_remaining(self) -> int:
        return max(0, self.available - self.total_used)

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        """Return a diagnostic snapshot of budget state."""
        result: Dict[str, Dict[str, int]] = {}
        for name, slot in self._slots.items():
            result[name] = {
                "limit": slot.limit,
                "used": slot.used,
                "remaining": slot.remaining,
            }
        result["_total"] = {
            "limit": self.available,
            "used": self.total_used,
            "remaining": self.total_remaining,
        }
        return result

    # ── config adjustment ────────────────────────────────────────────

    def set_context_window(self, tokens: int) -> None:
        """Update context window and recompute slot limits."""
        self.context_window = max(1024, tokens)
        self._recompute_limits()

    def set_response_reserve(self, tokens: int) -> None:
        """Update response reserve and recompute."""
        self.response_reserve = max(256, tokens)
        self._recompute_limits()

    # ── internals ────────────────────────────────────────────────────

    def _recompute_limits(self) -> None:
        avail = self.available
        for name, ratio in self.ratios.items():
            if name in self._slots:
                self._slots[name].limit = int(avail * ratio)
                self._slots[name].ratio = ratio
            else:
                self._slots[name] = _Slot(name=name, ratio=ratio, limit=int(avail * ratio))
