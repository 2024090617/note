"""
Agent Skills - Multi-location skill discovery and management.

Supports both project-level and personal skills following agentskills.io standard:
- Project skills: .github/skills/, .claude/skills/, .agents/skills/
- Personal skills: ~/.copilot/skills/, ~/.claude/skills/, ~/.agents/skills/

Project skills override personal skills with the same name.
"""

from .constants import (
    PROJECT_SKILL_DIRS,
    PERSONAL_SKILL_DIRS,
)
from .discovery import (
    discover_project_skills,
    discover_personal_skills,
    discover_all_skills,
    auto_detect_project_root,
)
from .manager import (
    create_skill_manager,
    MultiLocationSkillManager,
)

__all__ = [
    # Constants
    "PROJECT_SKILL_DIRS",
    "PERSONAL_SKILL_DIRS",
    # Discovery functions
    "discover_project_skills",
    "discover_personal_skills",
    "discover_all_skills",
    "auto_detect_project_root",
    # Manager
    "create_skill_manager",
    "MultiLocationSkillManager",
]
