"""Docker sandbox tools — run scripts in isolated containers."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import List, Optional

from digimate.core.types import ToolResult

_INTERPRETERS = {
    "python": "python3", "python3": "python3",
    "node": "node", "javascript": "node",
    "bash": "bash", "sh": "sh",
}
_EXTENSIONS = {
    "python": ".py", "python3": ".py",
    "node": ".js", "javascript": ".js",
    "bash": ".sh", "sh": ".sh",
}
_DEFAULT_IMAGES = {
    "python": "python:3.12-slim", "python3": "python:3.12-slim",
    "node": "node:20-slim", "javascript": "node:20-slim",
    "bash": "ubuntu:24.04", "sh": "alpine:3.19",
}


def make_sandbox_tools(workdir: str = ".", default_image: str = "python:3.12-slim"):
    """Return sandbox tool functions."""

    def docker_available() -> ToolResult:
        if not shutil.which("docker"):
            return ToolResult(False, "", "Docker CLI not found on PATH")
        try:
            r = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                return ToolResult(True, f"Docker available (server {r.stdout.strip()})")
            return ToolResult(False, "", f"Docker not running: {r.stderr.strip()}")
        except Exception as e:
            return ToolResult(False, "", str(e))

    def run_in_docker(
        script: str,
        language: str = "python",
        image: str = "",
        timeout: int = 120,
        pip_packages: Optional[List[str]] = None,
        network: bool = False,
    ) -> ToolResult:
        if not script.strip():
            return ToolResult(False, "", "script content is required")

        interp = _INTERPRETERS.get(language, language)
        ext = _EXTENSIONS.get(language, ".txt")
        img = image or _DEFAULT_IMAGES.get(language, default_image)

        if pip_packages:
            network = True

        sandbox_dir = Path(workdir) / ".agent_sandbox"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        name = f"sandbox_{uuid.uuid4().hex[:8]}{ext}"
        script_path = sandbox_dir / name

        try:
            script_path.write_text(script, encoding="utf-8")

            cmd = [
                "docker", "run", "--rm",
                "-v", f"{workdir}:/workspace", "-w", "/workspace",
                "--memory", "512m", "--cpus", "1.0", "--pids-limit", "100",
            ]
            if not network:
                cmd.extend(["--network", "none"])
            cmd.append(img)

            if pip_packages:
                pkgs = " ".join(pip_packages)
                cmd.extend(["sh", "-c",
                             f"pip install --quiet {pkgs} && {interp} /workspace/.agent_sandbox/{name}"])
            else:
                cmd.extend([interp, f"/workspace/.agent_sandbox/{name}"])

            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=workdir)

            output = r.stdout
            if r.stderr:
                output += f"\n[stderr]\n{r.stderr}"
            output = output.strip()
            if len(output) > 10_000:
                output = output[:10_000] + "\n... [truncated]"

            return ToolResult(
                r.returncode == 0, output,
                error=r.stderr.strip() if r.returncode != 0 else "",
                data={"image": img, "language": language, "returncode": r.returncode},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", f"Container timed out after {timeout}s")
        except FileNotFoundError:
            return ToolResult(False, "", "Docker CLI not found")
        except Exception as e:
            return ToolResult(False, "", str(e))
        finally:
            if script_path.exists():
                script_path.unlink()

    return {
        "docker_available": (docker_available, False),
        "run_in_docker":    (run_in_docker, True),
    }
