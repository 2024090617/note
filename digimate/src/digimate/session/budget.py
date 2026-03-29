"""Context budget manager for token-aware prompt construction.

Tracks token usage per component and enforces a configurable budget
so the agent never exceeds the model's context window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

# Allocation ratios (fractions of available = window - reserve)
_DEFAULT_RATIOS: Dict[str, float] = {
    "system_prompt": 0.15,
    "memory": 0.10,
    "working_memory": 0.05,
    "skills": 0.05,
    "mcp_tools": 0.05,
    "history": 0.60,
}


def estimate_tokens(text: str) -> int:
    """Fast token estimate, CJK-aware.

    English/code averages ~4 chars per token.
    CJK characters average ~1.5 chars per token.
    """
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff'
              or '\u3400' <= c <= '\u4dbf'
              or '\uf900' <= c <= '\ufaff')
    non_cjk = len(text) - cjk
    return max(1, non_cjk // 4 + cjk * 2 // 3)


@dataclass
class _Slot:
    name: str
    ratio: float
    limit: int = 0
    used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


@dataclass
class ContextBudgetManager:
    """Manages token budget across prompt components."""

    context_window: int = 128_000
    response_reserve: int = 4_096
    ratios: Dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_RATIOS))
    _slots: Dict[str, _Slot] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._recompute_limits()

    def reset(self) -> None:
        for slot in self._slots.values():
            slot.used = 0

    def record(self, component: str, text: str) -> int:
        tokens = estimate_tokens(text)
        slot = self._slots.get(component)
        if slot is None:
            slot = _Slot(name=component, ratio=0.0, limit=self.available)
            self._slots[component] = slot
        slot.used = tokens
        return tokens

    def limit(self, component: str) -> int:
        """Return the token limit for *component*."""
        slot = self._slots.get(component)
        return slot.limit if slot else self.available

    def remaining(self, component: str) -> int:
        slot = self._slots.get(component)
        return slot.remaining if slot else self.available

    def is_over_budget(self) -> bool:
        return self.total_used > self.available

    @property
    def available(self) -> int:
        return max(0, self.context_window - self.response_reserve)

    @property
    def total_used(self) -> int:
        return sum(s.used for s in self._slots.values())

    @property
    def total_remaining(self) -> int:
        return max(0, self.available - self.total_used)

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        result: Dict[str, Dict[str, int]] = {}
        for name, slot in self._slots.items():
            result[name] = {"limit": slot.limit, "used": slot.used, "remaining": slot.remaining}
        result["_total"] = {
            "limit": self.available,
            "used": self.total_used,
            "remaining": self.total_remaining,
        }
        return result

    def _recompute_limits(self) -> None:
        avail = self.available
        for name, ratio in self.ratios.items():
            if name in self._slots:
                self._slots[name].limit = int(avail * ratio)
                self._slots[name].ratio = ratio
            else:
                self._slots[name] = _Slot(name=name, ratio=ratio, limit=int(avail * ratio))
