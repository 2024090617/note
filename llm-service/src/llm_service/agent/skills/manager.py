"""
Skill manager - wrapper around skillkit SkillManager with multi-location support.

Manages skills from multiple directories with proper deduplication
(project skills override personal skills with same name).
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from .discovery import discover_all_skills

logger = logging.getLogger(__name__)

# Try to import skillkit
try:
    from skillkit import SkillManager
    SKILLKIT_AVAILABLE = True
except ImportError:
    SKILLKIT_AVAILABLE = False
    logger.debug("skillkit not available (optional dependency)")


class SkillInfo:
    """Lightweight skill info for deduplication."""
    
    def __init__(self, name: str, description: str, location: Path):
        self.name = name
        self.description = description
        self.location = location
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "location": str(self.location),
        }


class MultiLocationSkillManager:
    """
    Skill manager that supports multiple skill directories.
    
    Features:
    - Discovers skills from multiple locations
    - Deduplicates by name (first location wins)
    - Caches skill content for performance
    """
    
    def __init__(self, skill_dirs: List[Path]):
        """
        Initialize multi-location skill manager.
        
        Args:
            skill_dirs: List of skill directory paths (in priority order)
        """
        self.skill_dirs = skill_dirs
        self._managers: List[SkillManager] = []
        self._skill_cache: Dict[str, str] = {}
        self._skill_index: Dict[str, Path] = {}  # skill_name -> location
        
        # Create a SkillManager for each directory
        for skill_dir in skill_dirs:
            try:
                parent_dir = skill_dir.parent
                manager = SkillManager(
                    anthropic_config_dir=str(parent_dir),
                    project_skill_dir=""
                )
                manager.discover()
                self._managers.append(manager)
                logger.debug(f"Initialized SkillManager for {skill_dir}")
            except Exception as e:
                logger.warning(f"Failed to initialize SkillManager for {skill_dir}: {e}")
        
        self._build_skill_index()
    
    def _build_skill_index(self):
        """Build index of skills by name (first location wins)."""
        for i, manager in enumerate(self._managers):
            try:
                for skill in manager.list_skills():
                    if skill.name not in self._skill_index:
                        self._skill_index[skill.name] = self.skill_dirs[i]
                        logger.debug(f"Indexed skill: {skill.name} from {self.skill_dirs[i]}")
            except Exception as e:
                logger.warning(f"Failed to list skills from manager {i}: {e}")
    
    def list_skills(self) -> List[SkillInfo]:
        """List all available skills (deduplicated)."""
        skills_dict: Dict[str, SkillInfo] = {}
        
        for i, manager in enumerate(self._managers):
            try:
                for skill in manager.list_skills():
                    if skill.name not in skills_dict:
                        skills_dict[skill.name] = SkillInfo(
                            name=skill.name,
                            description=skill.description,
                            location=self.skill_dirs[i],
                        )
            except Exception as e:
                logger.warning(f"Error listing skills: {e}")
        
        return list(skills_dict.values())
    
    def invoke_skill(self, skill_name: str, arguments: str = "") -> Optional[str]:
        """
        Invoke a skill and get its content.
        
        Args:
            skill_name: Name of the skill
            arguments: Optional arguments
            
        Returns:
            Skill content as string, or None if not found
        """
        cache_key = f"{skill_name}:{arguments}"
        if cache_key in self._skill_cache:
            return self._skill_cache[cache_key]
        
        skill_location = self._skill_index.get(skill_name)
        if not skill_location:
            logger.warning(f"Skill not found: {skill_name}")
            return None
        
        try:
            manager_idx = self.skill_dirs.index(skill_location)
            manager = self._managers[manager_idx]
            result = manager.invoke_skill(skill_name, arguments)
            if result:
                self._skill_cache[cache_key] = result
                logger.debug(f"Invoked skill: {skill_name} from {skill_location}")
                return result
        except (ValueError, IndexError, Exception) as e:
            logger.warning(f"Failed to invoke skill {skill_name}: {e}")
        
        return None
    
    def get_skill_locations(self) -> Dict[str, Any]:
        """Get information about skill locations."""
        from .discovery import get_skill_info
        
        info = get_skill_info(self.skill_dirs)
        info["skill_count"] = len(self._skill_index)
        info["skills_by_location"] = {}
        
        for skill_name, location in self._skill_index.items():
            loc_str = str(location)
            if loc_str not in info["skills_by_location"]:
                info["skills_by_location"][loc_str] = []
            info["skills_by_location"][loc_str].append(skill_name)
        
        return info


def create_skill_manager(
    project_root: Optional[Path] = None
) -> Optional[MultiLocationSkillManager]:
    """
    Create a skill manager with multi-location discovery.
    
    This is the recommended way to initialize skill support.
    
    Args:
        project_root: Project root directory (auto-detected if None)
        
    Returns:
        MultiLocationSkillManager instance, or None if skillkit unavailable
    """
    if not SKILLKIT_AVAILABLE:
        logger.debug("Skillkit not available, skill manager disabled")
        return None
    
    skill_dirs = discover_all_skills(project_root)
    if not skill_dirs:
        logger.debug("No skill directories found")
        return None
    
    try:
        manager = MultiLocationSkillManager(skill_dirs)
        skill_count = len(manager.list_skills())
        logger.info(f"Skill manager initialized with {skill_count} skill(s) from {len(skill_dirs)} location(s)")
        return manager
    except Exception as e:
        logger.warning(f"Failed to create skill manager: {e}")
        return None
