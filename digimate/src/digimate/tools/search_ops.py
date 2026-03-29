"""Search and discovery tools."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from digimate.core.types import ToolResult


def make_search_tools(resolve_path):
    """Return search tool functions."""

    def search_files(pattern: str, path: str = ".") -> ToolResult:
        try:
            base = resolve_path(path)
            matches = list(base.glob(pattern))[:100]
            paths = [str(m.relative_to(base)) for m in matches]
            return ToolResult(True, "\n".join(paths),
                              data={"pattern": pattern, "count": len(paths)})
        except Exception as e:
            return ToolResult(False, "", str(e))

    def grep(
        pattern: str,
        path: str = ".",
        file_pattern: str = "*",
        ignore_case: bool = True,
    ) -> ToolResult:
        try:
            base = resolve_path(path)
            flags = re.IGNORECASE if ignore_case else 0
            regex = re.compile(pattern, flags)
            results = []
            searched = 0

            for fp in base.rglob(file_pattern):
                if not fp.is_file():
                    continue
                if any(p.startswith(".") for p in fp.parts):
                    continue
                if "node_modules" in fp.parts or "__pycache__" in fp.parts:
                    continue
                searched += 1
                try:
                    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                        for n, line in enumerate(f, 1):
                            if regex.search(line):
                                rel = fp.relative_to(base)
                                results.append(f"{rel}:{n}: {line.rstrip()}")
                                if len(results) >= 50:
                                    break
                except Exception:
                    pass
                if len(results) >= 50:
                    break

            output = "\n".join(results) if results else "No matches found"
            return ToolResult(True, output,
                              data={"pattern": pattern, "matches": len(results),
                                    "files_searched": searched})
        except Exception as e:
            return ToolResult(False, "", str(e))

    def ripgrep(
        pattern: str,
        path: str = ".",
        file_pattern: Optional[str] = None,
        ignore_case: bool = True,
        max_results: int = 50,
    ) -> ToolResult:
        """Use rg (ripgrep) if available, fallback to grep tool."""
        if not shutil.which("rg"):
            return grep(pattern, path, file_pattern or "*", ignore_case)

        base = resolve_path(path)
        cmd = ["rg", "--no-heading", "--line-number", f"--max-count={max_results}"]
        if ignore_case:
            cmd.append("-i")
        if file_pattern:
            cmd.extend(["-g", file_pattern])
        cmd.extend([pattern, str(base)])

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            output = proc.stdout.strip() or "No matches found"
            # Make paths relative
            output = output.replace(str(base) + "/", "")
            return ToolResult(True, output,
                              data={"pattern": pattern, "tool": "ripgrep"})
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", "ripgrep timed out")
        except Exception as e:
            return ToolResult(False, "", str(e))

    return {
        "search_files": (search_files, False),
        "grep":         (grep, False),
        "ripgrep":      (ripgrep, False),
    }
