"""Git operation tools."""

from __future__ import annotations

import subprocess

from digimate.core.types import ToolResult


def make_git_tools(workdir: str = "."):
    """Return git tool functions."""

    def _git(args: str, timeout: int = 30) -> ToolResult:
        try:
            result = subprocess.run(
                f"git {args}", shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=workdir,
            )
            output = result.stdout.strip()
            if result.returncode != 0:
                return ToolResult(False, output, error=result.stderr.strip())
            return ToolResult(True, output)
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", f"git {args} timed out")
        except Exception as e:
            return ToolResult(False, "", str(e))

    def git_status() -> ToolResult:
        return _git("status --short")

    def git_diff(path: str = "", staged: bool = False) -> ToolResult:
        cmd = "diff --cached" if staged else "diff"
        if path:
            cmd += f" -- {path}"
        return _git(cmd)

    def git_log(count: int = 10, oneline: bool = True) -> ToolResult:
        fmt = " --oneline" if oneline else ""
        return _git(f"log -{count}{fmt}")

    def git_branch() -> ToolResult:
        return _git("branch -a")

    def git_stash(action: str = "list") -> ToolResult:
        if action not in ("list", "push", "pop", "drop"):
            return ToolResult(False, "", f"Unknown stash action: {action}")
        return _git(f"stash {action}")

    def git_commit(message: str, all_tracked: bool = False) -> ToolResult:
        cmd = "commit"
        if all_tracked:
            cmd += " -a"
        cmd += f' -m "{message}"'
        return _git(cmd)

    def git_add(path: str = ".") -> ToolResult:
        return _git(f"add {path}")

    return {
        "git_status": (git_status, False),
        "git_diff":   (git_diff, False),
        "git_log":    (git_log, False),
        "git_branch": (git_branch, False),
        "git_stash":  (git_stash, True),
        "git_commit": (git_commit, True),
        "git_add":    (git_add, True),
    }
