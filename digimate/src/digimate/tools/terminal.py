"""Terminal command execution with Layer 2 output cap."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from digimate.core.types import ToolResult


def make_terminal_tools(resolve_path, *, workdir: str = ".", command_output_limit: int = 50_000):
    """Return terminal tool functions."""

    _RISKY = [
        r"\brm\s+-rf\b",
        r"\brmdir\b",
        r"\bdrop\s+database\b",
        r"\bdrop\s+table\b",
        r"\bgit\s+push\s+.*--force\b",
        r"\bgit\s+reset\s+--hard\b",
    ]

    def run_command(command: str, timeout: int = 60) -> ToolResult:
        is_risky = any(re.search(p, command, re.IGNORECASE) for p in _RISKY)
        if is_risky:
            return ToolResult(
                False,
                f"Risky command detected: {command}\nUse explicit confirmation.",
                data={"needs_confirmation": True},
            )

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=workdir,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            output = output.strip()

            # Layer 2 guard: cap stdout
            if len(output) > command_output_limit:
                overflow_dir = Path(workdir) / ".digimate" / "cache" / "overflow"
                overflow_dir.mkdir(parents=True, exist_ok=True)
                overflow_path = overflow_dir / f"cmd_output_{hash(command) & 0xFFFFFF:06x}.txt"
                overflow_path.write_text(output, encoding="utf-8")
                output = (
                    output[:command_output_limit]
                    + f"\n\n[Output truncated at {command_output_limit:,} chars. "
                    f"Full output: {overflow_path}]"
                )

            return ToolResult(
                result.returncode == 0, output,
                error=result.stderr if result.returncode != 0 else "",
                data={"command": command, "returncode": result.returncode},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(False, "", str(e))

    return {"run_command": (run_command, True)}
