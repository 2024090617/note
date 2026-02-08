"""Environment inspection tools."""

import re
import subprocess

from .types import ToolResult


class EnvironmentOpsMixin:
    """Environment inspection operations."""

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

        python_result = self._run_silent("python3 --version")
        if python_result:
            env_info["toolchains"]["python"] = python_result.strip()

        node_result = self._run_silent("node --version")
        if node_result:
            env_info["toolchains"]["node"] = node_result.strip()

        npm_result = self._run_silent("npm --version")
        if npm_result:
            env_info["toolchains"]["npm"] = npm_result.strip()

        java_result = self._run_silent("java -version 2>&1")
        if java_result and "version" in java_result.lower():
            match = re.search(r'"([^"]+)"', java_result)
            env_info["toolchains"]["java"] = match.group(1) if match else java_result.split("\n")[0]

        git_result = self._run_silent("git --version")
        if git_result:
            env_info["toolchains"]["git"] = git_result.strip()

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
            data=env_info,
        )

    def get_git_status(self) -> ToolResult:
        """Get git repository status."""
        if not (self.workdir / ".git").exists():
            return ToolResult(False, "Not a git repository")

        try:
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                cwd=str(self.workdir),
            )
            branch = branch_result.stdout.strip() or "detached"

            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=str(self.workdir),
            )

            changes = status_result.stdout.strip().split("\n") if status_result.stdout.strip() else []
            dirty = len(changes) > 0

            log_result = subprocess.run(
                ["git", "log", "--oneline", "-5"],
                capture_output=True,
                text=True,
                cwd=str(self.workdir),
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
                },
            )

        except Exception as e:
            return ToolResult(False, "", str(e))
