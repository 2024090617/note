"""
Tool registry and implementations for the Agent.

Organized into categorized modules for easier extension.
"""

from .registry import ToolRegistry
from .types import ToolResult

__all__ = [
    "ToolRegistry",
    "ToolResult",
]
