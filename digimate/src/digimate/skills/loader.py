"""Skill discovery — agentskills.io compatible, no skillkit dependency."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

# Directories to search for skills (relative to project root)
_PROJECT_SKILL_DIRS = [
    ".github/skills",
    ".claude/skills",
    ".agents/skills",
    ".digimate/skills",
]

# Personal skill directories (relative to ~)
_PERSONAL_SKILL_DIRS = [
    ".copilot/skills",
    ".claude/skills",
    ".agents/skills",
    ".digimate/skills",
]


@dataclass
class Skill:
    """A discovered skill."""

    name: str
    description: str
    path: Path
    source: str  # "project" or "personal"
    content: Optional[str] = None  # loaded lazily

    def load(self) -> str:
        if self.content is None:
            try:
                self.content = self.path.read_text(encoding="utf-8")
            except Exception:
                self.content = ""
        return self.content


def discover_skills(project_root: str) -> List[Skill]:
    """Discover all skills from project and personal directories.

    Project skills override personal skills with the same name.
    """
    root = Path(project_root).resolve()
    seen: Dict[str, Skill] = {}

    # Project skills (higher priority)
    for rel in _PROJECT_SKILL_DIRS:
        _scan_skill_dir(root / rel, "project", seen)

    # Personal skills (lower priority)
    home = Path.home()
    for rel in _PERSONAL_SKILL_DIRS:
        _scan_skill_dir(home / rel, "personal", seen)

    return list(seen.values())


def _scan_skill_dir(directory: Path, source: str, seen: Dict[str, Skill]):
    if not directory.is_dir():
        return
    for fp in sorted(directory.iterdir()):
        if fp.suffix.lower() != ".md" or not fp.is_file():
            continue
        name = fp.stem  # skill name from filename
        if name in seen:
            continue  # earlier (project) skills take priority
        desc = _extract_description(fp)
        seen[name] = Skill(name=name, description=desc, path=fp, source=source)


def _extract_description(path: Path) -> str:
    """Extract first paragraph or YAML description from a skill file."""
    try:
        text = path.read_text(encoding="utf-8")[:2000]
    except Exception:
        return ""

    # Try YAML front-matter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            front = text[3:end]
            m = re.search(r"description:\s*(.+)", front)
            if m:
                return m.group(1).strip().strip('"').strip("'")

    # Fallback: first non-heading, non-empty paragraph
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("---"):
            continue
        return line[:200]
    return ""


def render_skills_block(skills: List[Skill]) -> str:
    """Render an <available_skills> XML block for the system prompt."""
    if not skills:
        return ""
    lines = ["<available_skills>"]
    for s in skills:
        lines.append(f'  <skill name="{s.name}">{s.description}</skill>')
    lines.append("</available_skills>")
    return "\n".join(lines)
