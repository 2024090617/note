"""Abstract LLM client interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from digimate.core.types import ChatMessage, ChatResponse


class LLMClient(ABC):
    """Base class for all LLM backends."""

    @abstractmethod
    def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
    ) -> ChatResponse:
        """Send messages and get a completion."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the backend is reachable."""

    @abstractmethod
    def get_models(self) -> List[str]:
        """List available model names."""
