"""Instruction-file discovery (rules / copilot-instructions)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional


# Priority-ordered list of instruction file locations (relative to project root).
_PROJECT_INSTRUCTION_FILES: List[str] = [
    "CLAUDE.md",
    ".claude/CLAUDE.md",
    "CLAUDE.local.md",
    ".github/copilot-instructions.md",
]

# Glob patterns for rule directories
_PROJECT_RULE_GLOBS: List[str] = [
    ".digimate/rules/*.md",
    ".claude/rules/*.md",
    ".agents/rules/*.md",
]

# Personal instruction files (relative to ~)
_PERSONAL_FILES: List[str] = [
    ".claude/CLAUDE.md",
    ".digimate/rules",       # directory
    ".claude/rules",         # directory
]


def discover_instruction_files(
    project_root: str,
    personal: bool = True,
) -> Dict[str, str]:
    """Discover and read all instruction files.

    Returns a dict mapping source label → content.
    Files are returned in priority order; the caller decides
    how to inject them into the prompt.
    """
    root = Path(project_root).resolve()
    found: Dict[str, str] = {}

    # Project-level fixed files
    for relpath in _PROJECT_INSTRUCTION_FILES:
        fp = root / relpath
        if fp.is_file():
            found[relpath] = _safe_read(fp)

    # Project-level rule directories
    for glob_pat in _PROJECT_RULE_GLOBS:
        for fp in sorted(root.glob(glob_pat)):
            if fp.is_file():
                label = str(fp.relative_to(root))
                if label not in found:
                    found[label] = _safe_read(fp)

    # Personal / global instruction files
    if personal:
        home = Path.home()
        for relpath in _PERSONAL_FILES:
            p = home / relpath
            if p.is_file():
                found[f"~/{relpath}"] = _safe_read(p)
            elif p.is_dir():
                for fp in sorted(p.glob("*.md")):
                    label = f"~/{relpath}/{fp.name}"
                    if label not in found:
                        found[label] = _safe_read(fp)

    return found


def _safe_read(path: Path, max_bytes: int = 50_000) -> str:
    try:
        text = path.read_text(encoding="utf-8")
        if len(text) > max_bytes:
            text = text[:max_bytes] + "\n[... truncated]"
        return text
    except Exception:
        return ""
