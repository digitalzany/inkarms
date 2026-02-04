"""
InkArms Skills System.

Skills are portable instruction sets that teach InkArms how to handle specific tasks.
A skill consists of:
- SKILL.md: Natural language instructions for the AI
- skill.yaml: Metadata, keywords, and permissions

Usage:
    from inkarms.skills import SkillManager, get_skill_manager

    # Get the skill manager
    manager = get_skill_manager()

    # Load a skill by name
    skill = manager.get_skill("security-scan")

    # Search for skills
    results = manager.search("code review")

    # Get skills relevant to a query (for auto-discovery)
    skills = manager.get_skills_for_query("review this code for security issues")
"""

# Models
from inkarms.skills.models import (
    FilesystemPermissions,
    Skill,
    SkillFrontmatter,
    SkillIndex,
    SkillIndexEntry,
    SkillMetadata,
    SkillPermissions,
)

# Parser
from inkarms.skills.parser import (
    SkillParseError,
    SkillValidationError,
    parse_skill_directory,
    parse_skill_md,
    parse_skill_yaml,
    parse_yaml_frontmatter,
    validate_skill_directory,
)

# Loader
from inkarms.skills.loader import (
    SkillNotFoundError,
    discover_all_skills,
    discover_skills_in_directory,
    get_global_skills_dir,
    get_project_skills_dir,
    list_installed_skills,
    load_skill,
    load_skill_from_path,
    skill_exists,
)

# Index
from inkarms.skills.index import (
    get_index_path,
    get_skills_for_query,
    load_index,
    rebuild_index,
    remove_from_index,
    save_index,
    search_skills,
    update_index_entry,
)

# Manager
from inkarms.skills.manager import (
    SkillManager,
    get_skill_manager,
)

__all__ = [
    # Models
    "FilesystemPermissions",
    "Skill",
    "SkillFrontmatter",
    "SkillIndex",
    "SkillIndexEntry",
    "SkillMetadata",
    "SkillPermissions",
    # Parser
    "SkillParseError",
    "SkillValidationError",
    "parse_skill_directory",
    "parse_skill_md",
    "parse_skill_yaml",
    "parse_yaml_frontmatter",
    "validate_skill_directory",
    # Loader
    "SkillNotFoundError",
    "discover_all_skills",
    "discover_skills_in_directory",
    "get_global_skills_dir",
    "get_project_skills_dir",
    "list_installed_skills",
    "load_skill",
    "load_skill_from_path",
    "skill_exists",
    # Index
    "get_index_path",
    "get_skills_for_query",
    "load_index",
    "rebuild_index",
    "remove_from_index",
    "save_index",
    "search_skills",
    "update_index_entry",
    # Manager
    "SkillManager",
    "get_skill_manager",
]
