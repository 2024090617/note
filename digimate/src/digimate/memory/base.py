"""Memory entry and abstract strategy base types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class MemoryEntry:
    """A single memory record."""

    content: str
    topic: str = ""
    source: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "topic": self.topic,
            "source": self.source,
            "timestamp": self.timestamp,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> MemoryEntry:
        return cls(
            content=d.get("content", ""),
            topic=d.get("topic", ""),
            source=d.get("source", ""),
            timestamp=d.get("timestamp", ""),
            score=d.get("score", 0.0),
        )


class MemoryStrategy(ABC):
    """Abstract base for memory strategies."""

    def __init__(self, memory_dir: str, workdir: str = "."):
        self.memory_dir = memory_dir
        self.workdir = workdir

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def store(self, content: str, topic: Optional[str] = None) -> str: ...

    @abstractmethod
    def recall(self, query: str, limit: int = 5) -> List[MemoryEntry]: ...

    @abstractmethod
    def list_memories(self) -> List[str]: ...

    @abstractmethod
    def get_prompt_context(self, max_tokens: int = 0) -> str: ...
