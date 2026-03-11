"""Memory entry and abstract strategy base types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class MemoryEntry:
    """A single memory record."""

    content: str
    topic: str = ""  # e.g. "debugging", "conventions", "daily"
    source: str = ""  # file path or "agent"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    score: float = 0.0  # relevance score from search

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "topic": self.topic,
            "source": self.source,
            "timestamp": self.timestamp,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryEntry":
        return cls(
            content=d.get("content", ""),
            topic=d.get("topic", ""),
            source=d.get("source", ""),
            timestamp=d.get("timestamp", ""),
            score=d.get("score", 0.0),
        )


class MemoryStrategy(ABC):
    """
    Abstract base for memory strategies.

    Each strategy decides how memories are stored, indexed, retrieved,
    and injected into the system prompt.

    Args:
        memory_dir: Directory for persistent memory files.
        workdir: Agent working directory (project root).
    """

    def __init__(self, memory_dir: str, workdir: str = "."):
        self.memory_dir = memory_dir
        self.workdir = workdir

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this strategy (e.g. 'claude-code')."""
        ...

    @abstractmethod
    def initialize(self) -> None:
        """
        One-time setup: create dirs, load existing memories, build indexes.
        Called once when the agent starts.
        """
        ...

    @abstractmethod
    def store(self, content: str, topic: Optional[str] = None) -> str:
        """
        Persist a memory.

        Args:
            content: Text to remember.
            topic: Optional topic tag (e.g. 'debugging', 'conventions').

        Returns:
            Confirmation message.
        """
        ...

    @abstractmethod
    def recall(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        """
        Retrieve memories relevant to *query*.

        Args:
            query: Free-text search query.
            limit: Max results.

        Returns:
            List of MemoryEntry, most relevant first.
        """
        ...

    @abstractmethod
    def list_memories(self) -> List[str]:
        """
        List all memory sources / files.

        Returns:
            Human-readable list of memory locations.
        """
        ...

    @abstractmethod
    def get_prompt_context(self, max_tokens: int = 0) -> str:
        """
        Build a text block suitable for injection into the system prompt.

        Should return an XML-ish block like <memory>...</memory> that the
        LLM will see at the start of every turn.

        Args:
            max_tokens: Soft token budget. 0 means unlimited (legacy behaviour).
                        When > 0, implementations should truncate output to fit.
        """
        ...

    def flush(self) -> None:
        """
        Pre-compaction hook — persist any in-flight state.

        Called before context window compaction so the strategy can
        save important information that would otherwise be lost.
        Default is a no-op; strategies may override.
        """
        pass
