"""
Tool registry and implementations for the Agent.

Provides file operations, command execution, environment inspection, etc.
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass
import json
import re


@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    output: str
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class ToolRegistry:
    """
    Registry of tools available to the agent.
    
    Tools are functions that perform actions like reading files,
    running commands, searching, etc.
    """
    
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
    
    # ==================== File Operations ====================
    
    def read_file(self, path: str, start_line: int = 1, end_line: Optional[int] = None) -> ToolResult:
        """
        Read contents of a file.
        
        Args:
            path: File path (relative to workdir or absolute)
            start_line: Starting line number (1-indexed)
            end_line: Ending line number (inclusive, None for all)
            
        Returns:
            ToolResult with file contents
        """
        try:
            file_path = self._resolve_path(path)
            
            if not file_path.exists():
                return ToolResult(False, "", f"File not found: {path}")
            
            if not file_path.is_file():
                return ToolResult(False, "", f"Not a file: {path}")
            
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            
            # Apply line range
            start_idx = max(0, start_line - 1)
            end_idx = end_line if end_line else len(lines)
            selected_lines = lines[start_idx:end_idx]
            
            content = "".join(selected_lines)
            return ToolResult(
                True, 
                content,
                data={
                    "path": str(file_path),
                    "total_lines": len(lines),
                    "lines_read": len(selected_lines),
                    "start_line": start_line,
                    "end_line": end_idx,
                }
            )
            
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    def write_file(self, path: str, content: str, create_dirs: bool = True) -> ToolResult:
        """
        Write content to a file.
        
        Args:
            path: File path
            content: Content to write
            create_dirs: Create parent directories if needed
            
        Returns:
            ToolResult indicating success
        """
        try:
            file_path = self._resolve_path(path)
            
            if create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            return ToolResult(
                True,
                f"Wrote {len(content)} bytes to {path}",
                data={"path": str(file_path), "bytes": len(content)}
            )
            
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    def create_file(self, path: str, content: str = "") -> ToolResult:
        """Create a new file."""
        file_path = self._resolve_path(path)
        
        if file_path.exists():
            return ToolResult(False, "", f"File already exists: {path}")
        
        return self.write_file(path, content)
    
    def append_file(self, path: str, content: str) -> ToolResult:
        """Append content to a file."""
        try:
            file_path = self._resolve_path(path)
            
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(content)
            
            return ToolResult(
                True,
                f"Appended {len(content)} bytes to {path}",
                data={"path": str(file_path), "bytes": len(content)}
            )
            
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    def delete_file(self, path: str, confirmed: bool = False) -> ToolResult:
        """
        Delete a file. Requires confirmation.
        
        Args:
            path: File path
            confirmed: Whether deletion is confirmed
        """
        if not confirmed and self._confirm_destructive:
            self._pending_confirmation = {
                "action": "delete_file",
                "path": path,
            }
            return ToolResult(
                False,
                f"Confirm deletion of {path}? Use /confirm to proceed.",
                data={"needs_confirmation": True}
            )
        
        try:
            file_path = self._resolve_path(path)
            
            if not file_path.exists():
                return ToolResult(False, "", f"File not found: {path}")
            
            file_path.unlink()
            return ToolResult(True, f"Deleted {path}")
            
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    def list_directory(self, path: str = ".") -> ToolResult:
        """
        List contents of a directory.
        
        Args:
            path: Directory path
            
        Returns:
            ToolResult with directory listing
        """
        try:
            dir_path = self._resolve_path(path)
            
            if not dir_path.exists():
                return ToolResult(False, "", f"Directory not found: {path}")
            
            if not dir_path.is_dir():
                return ToolResult(False, "", f"Not a directory: {path}")
            
            entries = []
            for entry in sorted(dir_path.iterdir()):
                suffix = "/" if entry.is_dir() else ""
                entries.append(f"{entry.name}{suffix}")
            
            return ToolResult(
                True,
                "\n".join(entries),
                data={"path": str(dir_path), "count": len(entries)}
            )
            
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    # ==================== Search Operations ====================
    
    def search_files(self, pattern: str, path: str = ".") -> ToolResult:
        """
        Search for files matching a glob pattern.
        
        Args:
            pattern: Glob pattern (e.g., "**/*.py")
            path: Base path to search from
            
        Returns:
            ToolResult with matching file paths
        """
        try:
            base_path = self._resolve_path(path)
            matches = list(base_path.glob(pattern))
            
            # Limit results and make paths relative
            matches = matches[:100]
            relative_paths = [str(m.relative_to(base_path)) for m in matches]
            
            return ToolResult(
                True,
                "\n".join(relative_paths),
                data={"pattern": pattern, "count": len(relative_paths)}
            )
            
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    def grep_search(
        self, 
        pattern: str, 
        path: str = ".", 
        file_pattern: str = "*",
        ignore_case: bool = True,
    ) -> ToolResult:
        """
        Search for text pattern in files.
        
        Args:
            pattern: Regex pattern to search
            path: Base path
            file_pattern: Glob pattern for files to search
            ignore_case: Case insensitive search
            
        Returns:
            ToolResult with matching lines
        """
        try:
            base_path = self._resolve_path(path)
            flags = re.IGNORECASE if ignore_case else 0
            regex = re.compile(pattern, flags)
            
            results = []
            files_searched = 0
            
            for file_path in base_path.rglob(file_pattern):
                if not file_path.is_file():
                    continue
                if any(part.startswith('.') for part in file_path.parts):
                    continue  # Skip hidden directories
                if 'node_modules' in file_path.parts or '__pycache__' in file_path.parts:
                    continue
                
                files_searched += 1
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                rel_path = file_path.relative_to(base_path)
                                results.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                                
                                if len(results) >= 50:
                                    break
                except:
                    pass
                
                if len(results) >= 50:
                    break
            
            output = "\n".join(results) if results else "No matches found"
            return ToolResult(
                True,
                output,
                data={
                    "pattern": pattern,
                    "matches": len(results),
                    "files_searched": files_searched,
                }
            )
            
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    # ==================== Command Execution ====================
    
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
        # Check for risky commands
        risky_patterns = [
            r'\brm\s+-rf\b', r'\brmdir\b', r'\bdel\s+/[sfq]\b',
            r'\bdrop\s+database\b', r'\bdrop\s+table\b',
            r'\bgit\s+push\s+.*--force\b', r'\bgit\s+reset\s+--hard\b',
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
                data={"needs_confirmation": True}
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
                }
            )
            
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    def confirm_action(self) -> ToolResult:
        """Confirm pending destructive action."""
        if not self._pending_confirmation:
            return ToolResult(False, "No action pending confirmation")
        
        action = self._pending_confirmation
        self._pending_confirmation = None
        
        if action["action"] == "delete_file":
            return self.delete_file(action["path"], confirmed=True)
        elif action["action"] == "run_command":
            return self.run_command(action["command"], confirmed=True)
        else:
            return ToolResult(False, f"Unknown action: {action['action']}")
    
    # ==================== Environment Inspection ====================
    
    def detect_environment(self) -> ToolResult:
        """
        Detect development environment: languages, tools, versions.
        
        Returns:
            ToolResult with environment info
        """
        env_info = {
            "workdir": str(self.workdir),
            "toolchains": {},
            "project_type": [],
            "package_managers": [],
        }
        
        # Detect Python
        python_result = self._run_silent("python3 --version")
        if python_result:
            env_info["toolchains"]["python"] = python_result.strip()
        
        # Detect Node.js
        node_result = self._run_silent("node --version")
        if node_result:
            env_info["toolchains"]["node"] = node_result.strip()
        
        # Detect npm
        npm_result = self._run_silent("npm --version")
        if npm_result:
            env_info["toolchains"]["npm"] = npm_result.strip()
        
        # Detect Java
        java_result = self._run_silent("java -version 2>&1")
        if java_result and "version" in java_result.lower():
            # Extract version from output
            match = re.search(r'"([^"]+)"', java_result)
            env_info["toolchains"]["java"] = match.group(1) if match else java_result.split('\n')[0]
        
        # Detect Git
        git_result = self._run_silent("git --version")
        if git_result:
            env_info["toolchains"]["git"] = git_result.strip()
        
        # Check for project files
        project_files = {
            "pyproject.toml": "python",
            "setup.py": "python",
            "requirements.txt": "python",
            "package.json": "node",
            "tsconfig.json": "typescript",
            "pom.xml": "java-maven",
            "build.gradle": "java-gradle",
            "Cargo.toml": "rust",
            "go.mod": "go",
        }
        
        for filename, proj_type in project_files.items():
            if (self.workdir / filename).exists():
                env_info["project_type"].append(proj_type)
        
        # Format output
        lines = [f"Working Directory: {env_info['workdir']}", ""]
        
        lines.append("Toolchains:")
        for tool, version in env_info["toolchains"].items():
            lines.append(f"  • {tool}: {version}")
        
        if env_info["project_type"]:
            lines.append("")
            lines.append(f"Project Type: {', '.join(set(env_info['project_type']))}")
        
        return ToolResult(
            True,
            "\n".join(lines),
            data=env_info
        )
    
    def get_git_status(self) -> ToolResult:
        """Get git repository status."""
        if not (self.workdir / ".git").exists():
            return ToolResult(False, "Not a git repository")
        
        try:
            # Get current branch
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, cwd=str(self.workdir)
            )
            branch = branch_result.stdout.strip() or "detached"
            
            # Get status
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, cwd=str(self.workdir)
            )
            
            changes = status_result.stdout.strip().split('\n') if status_result.stdout.strip() else []
            dirty = len(changes) > 0
            
            # Get recent commits
            log_result = subprocess.run(
                ["git", "log", "--oneline", "-5"],
                capture_output=True, text=True, cwd=str(self.workdir)
            )
            
            output_lines = [
                f"Branch: {branch}",
                f"Status: {'dirty' if dirty else 'clean'} ({len(changes)} changes)",
            ]
            
            if changes:
                output_lines.append("\nChanged files:")
                for change in changes[:10]:
                    output_lines.append(f"  {change}")
            
            output_lines.append("\nRecent commits:")
            output_lines.append(log_result.stdout.strip())
            
            return ToolResult(
                True,
                "\n".join(output_lines),
                data={
                    "branch": branch,
                    "dirty": dirty,
                    "changes": changes,
                }
            )
            
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    # ==================== Helper Methods ====================
    
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
        except:
            return None
