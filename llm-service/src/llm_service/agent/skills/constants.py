"""
Constants for skill locations following agentskills.io standard.

Standard skill directories:
- Project skills (relative to project root): .github/skills/, .claude/skills/, .agents/skills/
- Personal skills (in user home): ~/.copilot/skills/, ~/.claude/skills/, ~/.agents/skills/
"""

from pathlib import Path
from typing import List

# Project-level skill directories (relative to project root)
PROJECT_SKILL_DIRS: List[str] = [
    ".github/skills",
    ".claude/skills",
    ".agents/skills",
]

# Personal skill directories (in user home directory)
PERSONAL_SKILL_DIRS: List[str] = [
    ".copilot/skills",
    ".claude/skills",
    ".agents/skills",
]


def get_home_dir() -> Path:
    """
    Get user home directory in a cross-platform way.
    
    Returns:
        Path to user home directory
    """
    return Path.home()


def expand_personal_skill_dir(rel_path: str) -> Path:
    """
    Expand a personal skill directory path (e.g., '.claude/skills' -> '~/.claude/skills').
    
    Args:
        rel_path: Relative path from home (e.g., '.claude/skills')
        
    Returns:
        Absolute Path object
    """
    return get_home_dir() / rel_path
