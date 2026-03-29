"""Light workspace scanner — detect languages, frameworks, structure."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# Signature files → language/framework
_SIGNATURES: Dict[str, str] = {
    "package.json": "node",
    "tsconfig.json": "typescript",
    "pyproject.toml": "python",
    "setup.py": "python",
    "Pipfile": "python",
    "requirements.txt": "python",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "java-maven",
    "build.gradle": "java-gradle",
    "build.gradle.kts": "kotlin-gradle",
    "Gemfile": "ruby",
    "composer.json": "php",
    "CMakeLists.txt": "cmake",
    "Makefile": "make",
    "Dockerfile": "docker",
    "docker-compose.yml": "docker-compose",
    "docker-compose.yaml": "docker-compose",
    ".editorconfig": "editorconfig",
    ".eslintrc.json": "eslint",
    ".prettierrc": "prettier",
    "tailwind.config.js": "tailwind",
    "tailwind.config.ts": "tailwind",
    "next.config.js": "nextjs",
    "next.config.mjs": "nextjs",
    "vite.config.ts": "vite",
    "webpack.config.js": "webpack",
    "angular.json": "angular",
    "svelte.config.js": "svelte",
}

_EXTENSION_LANG: Dict[str, str] = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "react", ".tsx": "react-ts",
    ".rs": "rust", ".go": "go", ".java": "java",
    ".rb": "ruby", ".php": "php", ".c": "c", ".cpp": "c++",
    ".cs": "c#", ".swift": "swift", ".kt": "kotlin",
    ".md": "markdown", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".json": "json",
    ".html": "html", ".css": "css", ".scss": "scss",
    ".sql": "sql", ".sh": "shell", ".bash": "shell",
}


@dataclass
class WorkspaceManifest:
    """Lightweight workspace scan result."""

    root: str = ""
    languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    structure: List[str] = field(default_factory=list)  # tree-like listing
    file_count: int = 0
    git_root: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root, "languages": self.languages,
            "frameworks": self.frameworks, "config_files": self.config_files,
            "structure": self.structure, "file_count": self.file_count,
            "git_root": self.git_root,
        }

    def render(self) -> str:
        """Return a compact text block for system prompt injection."""
        lines = [f"Root: {self.root}"]
        if self.git_root:
            lines.append(f"Git root: {self.git_root}")
        if self.languages:
            lines.append(f"Languages: {', '.join(self.languages)}")
        if self.frameworks:
            lines.append(f"Frameworks: {', '.join(self.frameworks)}")
        if self.structure:
            lines.append("Structure:")
            for s in self.structure:
                lines.append(f"  {s}")
        lines.append(f"Files: {self.file_count}")
        return "\n".join(lines)


_SKIP = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".ruff_cache", "dist", "build",
    ".next", ".nuxt", "target", ".digimate",
})


def scan_workspace(
    root: str,
    max_depth: int = 3,
    cache: bool = True,
) -> WorkspaceManifest:
    """Scan workspace and return manifest.

    If *cache* is True, writes result to ``.digimate/cache/workspace_manifest.json``
    and returns cached copy on subsequent calls (unless the directory mtime changed).
    """
    root_path = Path(root).resolve()
    cache_path = root_path / ".digimate" / "cache" / "workspace_manifest.json"

    if cache and cache_path.exists():
        try:
            data = json.loads(cache_path.read_text())
            m = WorkspaceManifest(**{k: v for k, v in data.items() if k != "_mtime"})
            # Simple staleness check: compare root dir mtime
            stored_mtime = data.get("_mtime", 0)
            current_mtime = root_path.stat().st_mtime
            if abs(current_mtime - stored_mtime) < 1.0:
                return m
        except Exception:
            pass

    langs: Set[str] = set()
    frameworks: Set[str] = set()
    configs: List[str] = []
    structure: List[str] = []
    count = 0

    git_root = _detect_git_root(root_path)

    def walk(p: Path, depth: int, prefix: str = ""):
        nonlocal count
        if depth > max_depth:
            return
        try:
            entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        for entry in entries:
            name = entry.name
            if name in _SKIP or name.startswith("."):
                continue

            rel = str(entry.relative_to(root_path))

            if entry.is_dir():
                structure.append(f"{prefix}{name}/")
                walk(entry, depth + 1, prefix + "  ")
            else:
                count += 1
                if depth <= 1:
                    structure.append(f"{prefix}{name}")
                # Signature detection
                if name in _SIGNATURES:
                    sig = _SIGNATURES[name]
                    if sig in ("docker", "docker-compose", "make", "cmake"):
                        frameworks.add(sig)
                    elif sig in ("editorconfig", "eslint", "prettier"):
                        configs.append(name)
                    elif sig in (
                        "nextjs", "vite", "webpack", "angular", "svelte", "tailwind",
                    ):
                        frameworks.add(sig)
                    else:
                        frameworks.add(sig)
                    configs.append(name)
                # Extension detection
                ext = entry.suffix.lower()
                if ext in _EXTENSION_LANG:
                    langs.add(_EXTENSION_LANG[ext])

    walk(root_path, 0)

    manifest = WorkspaceManifest(
        root=str(root_path),
        languages=sorted(langs),
        frameworks=sorted(frameworks),
        config_files=sorted(set(configs)),
        structure=structure[:80],  # cap
        file_count=count,
        git_root=git_root,
    )

    if cache:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            data = manifest.to_dict()
            data["_mtime"] = root_path.stat().st_mtime
            cache_path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    return manifest


def _detect_git_root(path: Path) -> Optional[str]:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5, cwd=str(path),
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None
