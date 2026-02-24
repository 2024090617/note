"""
Skill discovery logic - find skills across multiple locations.

Discovers skills from both project-level and personal directories,
with project skills taking precedence over personal skills.
"""

import logging
import subprocess
from pathlib import Path
from typing import List, Optional

from .constants import (
    PROJECT_SKILL_DIRS,
    PERSONAL_SKILL_DIRS,
    expand_personal_skill_dir,
)

logger = logging.getLogger(__name__)


def auto_detect_project_root() -> Path:
    """
    Auto-detect project root directory.
    
    Strategy:
    1. Try to find git root
    2. Fall back to current working directory
    
    Returns:
        Path to project root
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        git_root = result.stdout.strip()
        if git_root:
            logger.debug(f"Detected git root: {git_root}")
            return Path(git_root)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    cwd = Path.cwd()
    logger.debug(f"Using current directory as project root: {cwd}")
    return cwd


def discover_project_skills(project_root: Optional[Path] = None) -> List[Path]:
    """
    Discover project-level skill directories.
    
    Searches for skills in:
    - .github/skills/
    - .claude/skills/
    - .agents/skills/
    
    Args:
        project_root: Project root directory (auto-detected if None)
        
    Returns:
        List of existing skill directory paths (ordered by priority)
    """
    if project_root is None:
        project_root = auto_detect_project_root()
    
    found_dirs: List[Path] = []
    for skill_dir in PROJECT_SKILL_DIRS:
        skill_path = project_root / skill_dir
        if skill_path.exists() and skill_path.is_dir():
            found_dirs.append(skill_path)
            logger.debug(f"Found project skills: {skill_path}")
    
    return found_dirs


def discover_personal_skills() -> List[Path]:
    """
    Discover personal (user-level) skill directories.
    
    Searches for skills in:
    - ~/.copilot/skills/
    - ~/.claude/skills/
    - ~/.agents/skills/
    
    Returns:
        List of existing skill directory paths (ordered by priority)
    """
    found_dirs: List[Path] = []
    for skill_dir in PERSONAL_SKILL_DIRS:
        skill_path = expand_personal_skill_dir(skill_dir)
        if skill_path.exists() and skill_path.is_dir():
            found_dirs.append(skill_path)
            logger.debug(f"Found personal skills: {skill_path}")
    
    return found_dirs


def discover_all_skills(project_root: Optional[Path] = None) -> List[Path]:
    """
    Discover all skill directories (project + personal).
    
    Priority order (first takes precedence for same skill name):
    1. Project skills (.github/skills/, .claude/skills/, .agents/skills/)
    2. Personal skills (~/.copilot/skills/, ~/.claude/skills/, ~/.agents/skills/)
    
    Args:
        project_root: Project root directory (auto-detected if None)
        
    Returns:
        List of skill directory paths in priority order
    """
    all_dirs: List[Path] = []
    
    # Project skills first (higher priority)
    all_dirs.extend(discover_project_skills(project_root))
    # Personal skills second (lower priority)
    all_dirs.extend(discover_personal_skills())
    
    if all_dirs:
        logger.info(f"Discovered {len(all_dirs)} skill location(s)")
        for i, skill_dir in enumerate(all_dirs, 1):
            logger.debug(f"  {i}. {skill_dir}")
    else:
        logger.debug("No skill directories found")
    
    return all_dirs


def get_skill_info(skill_dirs: List[Path]) -> dict:
    """
    Get summary information about discovered skills.
    
    Args:
        skill_dirs: List of skill directory paths
        
    Returns:
        Dictionary with skill location information
    """
    project_paths = []
    personal_paths = []
    
    for path in skill_dirs:
        try:
            path.relative_to(Path.home())
            personal_paths.append(str(path))
        except ValueError:
            project_paths.append(str(path))
    
    return {
        "total_locations": len(skill_dirs),
        "project_locations": project_paths,
        "personal_locations": personal_paths,
    }
