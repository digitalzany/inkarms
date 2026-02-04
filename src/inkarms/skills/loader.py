"""
Skill loader for InkArms.

Discovers and loads skills from global and project directories.
"""

from pathlib import Path

from inkarms.skills.models import Skill, SkillIndexEntry
from inkarms.skills.parser import (
    SkillParseError,
    SkillValidationError,
    parse_skill_directory,
    validate_skill_directory,
)
from inkarms.storage.paths import get_project_inkarms_dir, get_skills_dir


class SkillNotFoundError(Exception):
    """Skill not found error."""

    def __init__(self, name: str, searched_paths: list[Path] | None = None):
        self.name = name
        self.searched_paths = searched_paths or []
        paths_str = ", ".join(str(p) for p in self.searched_paths)
        super().__init__(
            f"Skill not found: {name}" + (f" (searched: {paths_str})" if paths_str else "")
        )


def get_global_skills_dir() -> Path:
    """Get the global skills directory.

    Returns:
        Path to ~/.inkarms/skills/
    """
    return get_skills_dir()


def get_project_skills_dir(start_path: Path | None = None) -> Path | None:
    """Get the project's skills directory if it exists.

    Args:
        start_path: Starting path to search from (default: cwd).

    Returns:
        Path to .inkarms/skills/ if found, None otherwise.
    """
    project_dir = get_project_inkarms_dir(start_path)
    if project_dir:
        skills_dir = project_dir / "skills"
        if skills_dir.exists() and skills_dir.is_dir():
            return skills_dir
    return None


def discover_skills_in_directory(directory: Path) -> list[Path]:
    """Discover all skill directories in a directory.

    A valid skill directory contains skill.yaml and SKILL.md.

    Args:
        directory: Directory to search.

    Returns:
        List of paths to skill directories.
    """
    if not directory.exists() or not directory.is_dir():
        return []

    skill_dirs = []
    for item in directory.iterdir():
        if item.is_dir():
            skill_yaml = item / "skill.yaml"
            skill_md = item / "SKILL.md"
            if skill_yaml.exists() and skill_md.exists():
                skill_dirs.append(item)

    return skill_dirs


def discover_all_skills(include_project: bool = True) -> list[tuple[Path, bool]]:
    """Discover all skills in global and project directories.

    Args:
        include_project: Whether to include project-level skills.

    Returns:
        List of tuples (skill_path, is_global).
    """
    skills = []

    # Discover global skills
    global_dir = get_global_skills_dir()
    for skill_path in discover_skills_in_directory(global_dir):
        skills.append((skill_path, True))

    # Discover project skills
    if include_project:
        project_dir = get_project_skills_dir()
        if project_dir:
            for skill_path in discover_skills_in_directory(project_dir):
                # Project skills override global skills with same name
                skills.append((skill_path, False))

    return skills


def load_skill(name_or_path: str, project_path: Path | None = None) -> Skill:
    """Load a skill by name or path.

    Resolution order:
    1. If it's a path (contains / or starts with . or ~), load from path
    2. Look in project skills directory (.inkarms/skills/)
    3. Look in global skills directory (~/.inkarms/skills/)

    Args:
        name_or_path: Skill name or path to skill directory.
        project_path: Optional project path for context.

    Returns:
        Loaded Skill object.

    Raises:
        SkillNotFoundError: If skill not found.
        SkillParseError: If skill exists but cannot be parsed.
    """
    searched_paths: list[Path] = []

    # Check if it's a path
    if "/" in name_or_path or name_or_path.startswith(".") or name_or_path.startswith("~"):
        skill_path = Path(name_or_path).expanduser().resolve()
        if skill_path.exists():
            return parse_skill_directory(skill_path)
        raise SkillNotFoundError(name_or_path, [skill_path])

    # It's a name - search in standard locations
    name = name_or_path

    # Search project skills first (higher priority)
    project_skills_dir = get_project_skills_dir(project_path)
    if project_skills_dir:
        project_skill_path = project_skills_dir / name
        searched_paths.append(project_skill_path)
        if project_skill_path.exists() and project_skill_path.is_dir():
            return parse_skill_directory(project_skill_path)

    # Search global skills
    global_skills_dir = get_global_skills_dir()
    global_skill_path = global_skills_dir / name
    searched_paths.append(global_skill_path)
    if global_skill_path.exists() and global_skill_path.is_dir():
        return parse_skill_directory(global_skill_path)

    raise SkillNotFoundError(name, searched_paths)


def load_skill_from_path(skill_path: Path) -> Skill:
    """Load a skill from a specific path.

    Args:
        skill_path: Path to the skill directory.

    Returns:
        Loaded Skill object.

    Raises:
        SkillParseError: If skill cannot be parsed.
    """
    return parse_skill_directory(skill_path)


def list_installed_skills(include_project: bool = True) -> list[SkillIndexEntry]:
    """List all installed skills.

    Args:
        include_project: Whether to include project-level skills.

    Returns:
        List of skill index entries.
    """
    entries = []
    seen_names: set[str] = set()

    # Get all skill directories
    all_skills = discover_all_skills(include_project)

    for skill_path, is_global in all_skills:
        try:
            skill = parse_skill_directory(skill_path)

            # Skip if we've already seen this name (project overrides global)
            if skill.name in seen_names:
                continue
            seen_names.add(skill.name)

            entry = SkillIndexEntry(
                name=skill.name,
                version=skill.metadata.version,
                description=skill.metadata.description,
                keywords=skill.metadata.keywords,
                path=str(skill_path),
                is_global=is_global,
            )
            entries.append(entry)

        except (SkillParseError, SkillValidationError):
            # Skip invalid skills in listing
            continue

    return entries


def skill_exists(name: str, project_path: Path | None = None) -> bool:
    """Check if a skill exists by name.

    Args:
        name: Skill name.
        project_path: Optional project path for context.

    Returns:
        True if skill exists, False otherwise.
    """
    # Check project skills
    project_skills_dir = get_project_skills_dir(project_path)
    if project_skills_dir:
        if (project_skills_dir / name).exists():
            return True

    # Check global skills
    global_skills_dir = get_global_skills_dir()
    if (global_skills_dir / name).exists():
        return True

    return False
