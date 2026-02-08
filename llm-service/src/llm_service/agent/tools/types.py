"""Shared types for tools."""

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class ToolResult:
    """Result from a tool execution."""

    success: bool
    output: str
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
