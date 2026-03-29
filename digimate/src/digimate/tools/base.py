"""Tool registry — flat, declarative tool registration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from digimate.core.types import ToolResult


@dataclass
class ToolDef:
    """Definition of a registered tool."""

    name: str
    fn: Callable[..., ToolResult]
    description: str = ""
    schema: Dict[str, Any] = field(default_factory=dict)
    category: str = "general"
    mutating: bool = False  # True → blocked in read-only mode


class ToolRegistry:
    """Flat tool registry with execute and mutating-guard support.

    Usage::

        reg = ToolRegistry(workdir="/project")
        reg.register("read_file", read_file_fn, mutating=False)
        reg.register("write_file", write_file_fn, mutating=True)
        result = reg.execute("read_file", {"path": "foo.py"})
    """

    def __init__(self, workdir: str = ".") -> None:
        self.workdir = Path(workdir).resolve()
        self._tools: Dict[str, ToolDef] = {}
        self._confirm_destructive = True
        self._pending_confirmation: Optional[Dict[str, Any]] = None

    def register(
        self,
        name: str,
        fn: Callable[..., ToolResult],
        description: str = "",
        schema: Optional[Dict[str, Any]] = None,
        category: str = "general",
        mutating: bool = False,
    ) -> None:
        self._tools[name] = ToolDef(
            name=name, fn=fn, description=description,
            schema=schema or {}, category=category, mutating=mutating,
        )

    def execute(self, name: str, params: Dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(False, "", f"Unknown tool: {name}")
        try:
            return tool.fn(**params)
        except TypeError as e:
            return ToolResult(False, "", f"Bad params for {name}: {e}")
        except Exception as e:
            return ToolResult(False, "", str(e))

    def get(self, name: str) -> Optional[ToolDef]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDef]:
        return list(self._tools.values())

    def mutating_tools(self) -> frozenset[str]:
        return frozenset(t.name for t in self._tools.values() if t.mutating)

    def resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return (self.workdir / p).resolve()
