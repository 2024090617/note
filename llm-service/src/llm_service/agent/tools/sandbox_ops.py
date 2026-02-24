"""Docker sandbox tools - run scripts in isolated containers."""

import logging
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

from .types import ToolResult

logger = logging.getLogger(__name__)

# Default resource limits
DEFAULT_MEMORY = "512m"
DEFAULT_CPUS = "1.0"
DEFAULT_PIDS = "100"
DEFAULT_TIMEOUT = 120

# Interpreter map for supported languages
INTERPRETERS = {
    "python": "python3",
    "python3": "python3",
    "node": "node",
    "javascript": "node",
    "bash": "bash",
    "sh": "sh",
}

# File extensions for generated scripts
EXTENSIONS = {
    "python": ".py",
    "python3": ".py",
    "node": ".js",
    "javascript": ".js",
    "bash": ".sh",
    "sh": ".sh",
}


class SandboxOpsMixin:
    """Docker sandbox operations for isolated script execution."""

    def docker_available(self) -> ToolResult:
        """Check if Docker daemon is running and accessible."""
        docker_bin = shutil.which("docker")
        if not docker_bin:
            return ToolResult(False, "", "Docker CLI not found on PATH")

        try:
            result = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                return ToolResult(True, f"Docker available (server {version})")
            return ToolResult(False, "", f"Docker not running: {result.stderr.strip()}")
        except Exception as e:
            return ToolResult(False, "", f"Docker check failed: {e}")

    def docker_search(self, query: str, limit: int = 5) -> ToolResult:
        """
        Search Docker Hub for images.

        Args:
            query: Search term (e.g. "python", "node", "latex")
            limit: Max results (default 5)

        Returns:
            ToolResult with formatted search results
        """
        if not query:
            return ToolResult(False, "", "query is required")

        try:
            result = subprocess.run(
                ["docker", "search", "--limit", str(limit),
                 "--format", "{{.Name}}\t{{.Description}}\t{{.StarCount}}\t{{.IsOfficial}}",
                 query],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return ToolResult(False, "", f"Search failed: {result.stderr.strip()}")

            lines = ["Name | Description | Stars | Official"]
            lines.append("-" * 60)
            for line in result.stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) >= 4:
                    name, desc, stars, official = parts[0], parts[1][:60], parts[2], parts[3]
                    off = "✓" if official.strip().lower() in ("true", "[ok]") else ""
                    lines.append(f"{name} | {desc} | ★{stars} | {off}")

            return ToolResult(True, "\n".join(lines))
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", "Docker search timed out")
        except Exception as e:
            return ToolResult(False, "", str(e))

    def docker_pull(self, image: str) -> ToolResult:
        """
        Pull a Docker image if not already cached locally.

        Args:
            image: Image name with optional tag (e.g. "python:3.12-slim")

        Returns:
            ToolResult with pull status
        """
        if not image:
            return ToolResult(False, "", "image is required")

        # Check if already available
        try:
            check = subprocess.run(
                ["docker", "images", "-q", image],
                capture_output=True, text=True, timeout=10,
            )
            if check.stdout.strip():
                return ToolResult(True, f"Image '{image}' already available locally")
        except Exception:
            pass

        # Pull
        try:
            result = subprocess.run(
                ["docker", "pull", image],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                return ToolResult(True, f"Pulled image '{image}' successfully")
            return ToolResult(False, "", f"Pull failed: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", f"Pull timed out for '{image}'")
        except Exception as e:
            return ToolResult(False, "", str(e))

    def run_in_docker(
        self,
        script: str,
        language: str = "python",
        image: str = "",
        timeout: int = DEFAULT_TIMEOUT,
        pip_packages: Optional[List[str]] = None,
        network: bool = False,
    ) -> ToolResult:
        """
        Run a script inside a Docker container with workdir mounted.

        The agent's workdir is bind-mounted at /workspace so generated
        files (docx, pdf, etc.) appear locally after execution.

        Args:
            script: Script source code to execute
            language: Language/interpreter (python, node, bash)
            image: Docker image to use (auto-selected if empty)
            timeout: Execution timeout in seconds
            pip_packages: Python packages to install before running
            network: Allow network access (auto-enabled if pip_packages set)

        Returns:
            ToolResult with stdout/stderr from the container
        """
        if not script.strip():
            return ToolResult(False, "", "script content is required")

        interpreter = INTERPRETERS.get(language, language)
        ext = EXTENSIONS.get(language, ".txt")

        # Auto-select image
        if not image:
            image = self._default_image_for(language)

        # Enable network if pip packages need to be installed
        if pip_packages:
            network = True

        # Prepare sandbox dir and script file
        sandbox_dir = Path(str(self.workdir)) / ".agent_sandbox"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        script_name = f"sandbox_{uuid.uuid4().hex[:8]}{ext}"
        script_path = sandbox_dir / script_name

        try:
            script_path.write_text(script, encoding="utf-8")

            # Build docker run command
            cmd = self._build_docker_cmd(
                image=image,
                script_container_path=f"/workspace/.agent_sandbox/{script_name}",
                interpreter=interpreter,
                pip_packages=pip_packages,
                network=network,
            )

            logger.info(f"Running in Docker: {image} ({language})")
            logger.debug(f"Docker command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=timeout,
                cwd=str(self.workdir),
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            output = output.strip()

            # Truncate very long output
            if len(output) > 10000:
                output = output[:10000] + "\n... [truncated]"

            return ToolResult(
                success=result.returncode == 0,
                output=output,
                error=result.stderr.strip() if result.returncode != 0 else None,
                data={
                    "image": image,
                    "language": language,
                    "returncode": result.returncode,
                },
            )

        except subprocess.TimeoutExpired:
            return ToolResult(False, "", f"Container timed out after {timeout}s")
        except FileNotFoundError:
            return ToolResult(False, "", "Docker CLI not found. Is Docker installed?")
        except Exception as e:
            return ToolResult(False, "", f"Sandbox execution failed: {e}")
        finally:
            # Cleanup script (keep sandbox dir for output files)
            if script_path.exists():
                script_path.unlink()

    def _build_docker_cmd(
        self,
        image: str,
        script_container_path: str,
        interpreter: str,
        pip_packages: Optional[List[str]] = None,
        network: bool = False,
    ) -> List[str]:
        """Build the full docker run command."""
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{self.workdir}:/workspace",
            "-w", "/workspace",
            "--memory", DEFAULT_MEMORY,
            "--cpus", DEFAULT_CPUS,
            "--pids-limit", DEFAULT_PIDS,
        ]

        if not network:
            cmd.extend(["--network", "none"])

        cmd.append(image)

        # If pip packages needed, chain install + run
        if pip_packages:
            pkgs = " ".join(pip_packages)
            cmd.extend([
                "sh", "-c",
                f"pip install --quiet {pkgs} && {interpreter} {script_container_path}",
            ])
        else:
            cmd.extend([interpreter, script_container_path])

        return cmd

    @staticmethod
    def _default_image_for(language: str) -> str:
        """Pick a sensible default Docker image for a language."""
        defaults = {
            "python": "python:3.12-slim",
            "python3": "python:3.12-slim",
            "node": "node:20-slim",
            "javascript": "node:20-slim",
            "bash": "ubuntu:24.04",
            "sh": "alpine:3.19",
        }
        return defaults.get(language, "python:3.12-slim")
