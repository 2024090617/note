"""Base tool registry utilities."""

from pathlib import Path
from typing import Optional, Dict, Any
import subprocess

from .types import ToolResult


class BaseToolRegistry:
    """Base registry with shared state and helpers."""

    def __init__(self, workdir: str = "."):
        """
        Initialize tool registry.

        Args:
            workdir: Working directory for file operations
        """
        self.workdir = Path(workdir).resolve()
        self._confirm_destructive = True
        self._pending_confirmation: Optional[Dict[str, Any]] = None

    def set_workdir(self, path: str):
        """Set working directory."""
        self.workdir = Path(path).resolve()

    def confirm_action(self) -> ToolResult:
        """Confirm pending destructive action."""
        if not self._pending_confirmation:
            return ToolResult(False, "No action pending confirmation")

        action = self._pending_confirmation
        self._pending_confirmation = None

        if action["action"] == "delete_file":
            return self.delete_file(action["path"], confirmed=True)
        if action["action"] == "run_command":
            return self.run_command(action["command"], confirmed=True)
        return ToolResult(False, f"Unknown action: {action['action']}")

    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to workdir."""
        p = Path(path)
        if p.is_absolute():
            return p
        return (self.workdir / p).resolve()

    def _run_silent(self, command: str) -> Optional[str]:
        """Run a command silently, return output or None."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None
