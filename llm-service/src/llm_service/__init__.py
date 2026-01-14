"""
LLM Service - Command-line LLM service using GitHub Copilot API
"""

from .client import LLMClient, Message, MessageRole, ChatResponse
from .config import Config

__version__ = "0.1.0"
__all__ = ["LLMClient", "Message", "MessageRole", "ChatResponse", "Config"]
