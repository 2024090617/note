"""Command execution tools."""

import re
import subprocess

from .types import ToolResult


class CommandOpsMixin:
    """Command execution operations."""

    def run_command(
        self,
        command: str,
        timeout: int = 60,
        confirmed: bool = False,
    ) -> ToolResult:
        """
        Run a shell command.

        Args:
            command: Command to run
            timeout: Timeout in seconds
            confirmed: Whether risky commands are confirmed

        Returns:
            ToolResult with command output
        """
        risky_patterns = [
            r"\brm\s+-rf\b",
            r"\brmdir\b",
            r"\bdel\s+/[sfq]\b",
            r"\bdrop\s+database\b",
            r"\bdrop\s+table\b",
            r"\bgit\s+push\s+.*--force\b",
            r"\bgit\s+reset\s+--hard\b",
        ]

        is_risky = any(re.search(p, command, re.IGNORECASE) for p in risky_patterns)

        if is_risky and not confirmed and self._confirm_destructive:
            self._pending_confirmation = {
                "action": "run_command",
                "command": command,
            }
            return ToolResult(
                False,
                f"⚠️  Risky command detected: {command}\nUse /confirm to proceed.",
                data={"needs_confirmation": True},
            )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.workdir),
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"

            return ToolResult(
                result.returncode == 0,
                output.strip(),
                error=result.stderr if result.returncode != 0 else None,
                data={
                    "command": command,
                    "returncode": result.returncode,
                },
            )

        except subprocess.TimeoutExpired:
            return ToolResult(False, "", f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(False, "", str(e))
