"""
Skill manager for InkArms.

Provides the main interface for working with skills.
"""

import shutil
from pathlib import Path
from typing import Any

from inkarms.skills.index import (
    get_skills_for_query,
    load_index,
    rebuild_index,
    remove_from_index,
    save_index,
    search_skills,
    update_index_entry,
)
from inkarms.skills.loader import (
    SkillNotFoundError,
    discover_all_skills,
    get_global_skills_dir,
    get_project_skills_dir,
    list_installed_skills,
    load_skill,
    load_skill_from_path,
    skill_exists,
)
from inkarms.skills.models import Skill, SkillIndex, SkillIndexEntry
from inkarms.skills.parser import (
    SkillParseError,
    SkillValidationError,
    parse_skill_directory,
    validate_skill_directory,
)


# Default skill templates
SKILL_YAML_TEMPLATE = """name: {name}
version: 1.0.0
description: {description}

keywords:
  - {keyword1}
  - {keyword2}

permissions:
  tools:
    - file_read
  network: false
  filesystem:
    read:
      - "*"
    write: []
"""

SKILL_MD_TEMPLATE = """---
name: {name}
description: {description}
---

# {title}

{description}

## When to Use

- Use case 1
- Use case 2

## Instructions

1. First, analyze the input
2. Then, apply the skill
3. Finally, deliver results

## Output Format

Return results as:
- A brief summary
- Detailed findings
- Recommendations
"""


class SkillManager:
    """Main interface for working with skills.

    Provides methods to:
    - Load skills by name or path
    - Search for skills by keyword
    - Create new skills from templates
    - Install and remove skills
    - Manage the skill index
    """

    def __init__(self, project_path: Path | None = None):
        """Initialize the skill manager.

        Args:
            project_path: Optional project path for context.
        """
        self.project_path = project_path
        self._index: SkillIndex | None = None

    @property
    def index(self) -> SkillIndex:
        """Get the skill index (lazy loaded)."""
        if self._index is None:
            self._index = load_index()
        return self._index

    def refresh_index(self) -> None:
        """Refresh the index from disk."""
        self._index = load_index()

    def get_skill(self, name_or_path: str) -> Skill:
        """Load a skill by name or path.

        Args:
            name_or_path: Skill name or path.

        Returns:
            Loaded Skill object.

        Raises:
            SkillNotFoundError: If skill not found.
            SkillParseError: If skill cannot be parsed.
        """
        return load_skill(name_or_path, self.project_path)

    def search(self, query: str, max_results: int = 5) -> list[SkillIndexEntry]:
        """Search for skills by keyword.

        Args:
            query: Search query.
            max_results: Maximum results to return.

        Returns:
            List of matching skill entries.
        """
        return search_skills(query, max_results)

    def get_skills_for_query(self, query: str, max_skills: int = 3) -> list[Skill]:
        """Get skills relevant to a user query.

        This is the main method for automatic skill discovery.
        It finds relevant skills and loads them.

        Args:
            query: User's query/prompt.
            max_skills: Maximum number of skills.

        Returns:
            List of loaded skills.
        """
        entries = get_skills_for_query(query, max_skills)
        skills = []

        for entry in entries:
            try:
                skill = load_skill_from_path(Path(entry.path))
                skills.append(skill)
            except (SkillParseError, SkillValidationError):
                # Skip skills that fail to load
                continue

        return skills

    def list_skills(self, include_project: bool = True) -> list[SkillIndexEntry]:
        """List all installed skills.

        Args:
            include_project: Whether to include project-level skills.

        Returns:
            List of skill index entries.
        """
        return list_installed_skills(include_project)

    def create_skill(
        self,
        name: str,
        description: str = "A new skill",
        location: str = "global",
    ) -> Path:
        """Create a new skill from template.

        Args:
            name: Skill name (used as directory name).
            description: Short description.
            location: Where to create ("global" or "project").

        Returns:
            Path to the created skill directory.

        Raises:
            ValueError: If skill already exists or location invalid.
        """
        # Validate name
        if not name or "/" in name or "\\" in name:
            raise ValueError(f"Invalid skill name: {name}")

        # Determine target directory
        if location == "global":
            skills_dir = get_global_skills_dir()
        elif location == "project":
            skills_dir = get_project_skills_dir(self.project_path)
            if skills_dir is None:
                # Create project skills directory
                if self.project_path:
                    skills_dir = self.project_path / ".inkarms" / "skills"
                else:
                    skills_dir = Path.cwd() / ".inkarms" / "skills"
        else:
            raise ValueError(f"Invalid location: {location} (use 'global' or 'project')")

        # Check if skill already exists
        skill_path = skills_dir / name
        if skill_path.exists():
            raise ValueError(f"Skill already exists: {skill_path}")

        # Create directory
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_path.mkdir(parents=True, exist_ok=True)

        # Create skill.yaml
        keyword1 = name.split("-")[0] if "-" in name else name
        keyword2 = name.split("-")[1] if "-" in name else "example"

        skill_yaml_content = SKILL_YAML_TEMPLATE.format(
            name=name,
            description=description,
            keyword1=keyword1,
            keyword2=keyword2,
        )
        (skill_path / "skill.yaml").write_text(skill_yaml_content)

        # Create SKILL.md
        title = name.replace("-", " ").replace("_", " ").title()
        skill_md_content = SKILL_MD_TEMPLATE.format(
            name=name,
            description=description,
            title=title,
        )
        (skill_path / "SKILL.md").write_text(skill_md_content)

        # Update index
        try:
            update_index_entry(skill_path, is_global=(location == "global"))
            self._index = None  # Invalidate cache
        except SkillParseError:
            pass  # Index update is optional

        return skill_path

    def install_skill(self, source: str, force: bool = False) -> Path:
        """Install a skill from a source.

        Currently supports:
        - Local path (directory containing skill.yaml)

        Future support:
        - github:user/repo/skill-name
        - URL

        Args:
            source: Skill source (path, github:..., or URL).
            force: Overwrite existing skill.

        Returns:
            Path to the installed skill.

        Raises:
            ValueError: If source is invalid.
            SkillParseError: If source is not a valid skill.
        """
        # Currently only support local paths
        if source.startswith("github:") or source.startswith("http"):
            raise NotImplementedError(f"Remote skill installation not yet implemented: {source}")

        # Local path installation
        source_path = Path(source).expanduser().resolve()

        if not source_path.exists():
            raise ValueError(f"Source path does not exist: {source_path}")

        if not source_path.is_dir():
            raise ValueError(f"Source is not a directory: {source_path}")

        # Validate the source skill
        issues = validate_skill_directory(source_path)
        errors = [i for i in issues if not i.startswith("Warning:")]
        if errors:
            raise SkillParseError(f"Invalid skill: {', '.join(errors)}", source_path)

        # Parse to get the name
        skill = parse_skill_directory(source_path)

        # Determine destination
        dest_path = get_global_skills_dir() / skill.name

        if dest_path.exists():
            if not force:
                raise ValueError(f"Skill already exists: {skill.name}. Use --force to overwrite.")
            shutil.rmtree(dest_path)

        # Copy the skill
        shutil.copytree(source_path, dest_path)

        # Update index
        try:
            update_index_entry(dest_path, is_global=True)
            self._index = None  # Invalidate cache
        except SkillParseError:
            pass

        return dest_path

    def remove_skill(self, name: str, confirm: bool = True) -> bool:
        """Remove an installed skill.

        Args:
            name: Skill name.
            confirm: If True, skill must exist.

        Returns:
            True if removed, False if not found.

        Raises:
            SkillNotFoundError: If confirm=True and skill not found.
        """
        # Check global skills first
        global_path = get_global_skills_dir() / name
        if global_path.exists():
            shutil.rmtree(global_path)
            remove_from_index(name)
            self._index = None  # Invalidate cache
            return True

        # Check project skills
        project_dir = get_project_skills_dir(self.project_path)
        if project_dir:
            project_path = project_dir / name
            if project_path.exists():
                shutil.rmtree(project_path)
                remove_from_index(name)
                self._index = None
                return True

        if confirm:
            raise SkillNotFoundError(name)

        return False

    def validate_skill(self, path: Path) -> list[str]:
        """Validate a skill directory.

        Args:
            path: Path to skill directory.

        Returns:
            List of validation issues (empty if valid).
        """
        return validate_skill_directory(path)

    def reindex(self, include_project: bool = True) -> SkillIndex:
        """Rebuild the skill index.

        Args:
            include_project: Whether to include project skills.

        Returns:
            The rebuilt index.
        """
        self._index = rebuild_index(include_project)
        return self._index

    def get_skill_info(self, name: str) -> dict[str, Any]:
        """Get detailed information about a skill.

        Args:
            name: Skill name.

        Returns:
            Dictionary with skill details.

        Raises:
            SkillNotFoundError: If skill not found.
        """
        skill = self.get_skill(name)

        return {
            "name": skill.name,
            "version": skill.metadata.version,
            "description": skill.metadata.description,
            "author": skill.metadata.author,
            "license": skill.metadata.license,
            "repository": skill.metadata.repository,
            "keywords": skill.metadata.keywords,
            "permissions": {
                "tools": skill.permissions.tools,
                "network": skill.permissions.network,
                "filesystem": {
                    "read": skill.permissions.filesystem.read,
                    "write": skill.permissions.filesystem.write,
                },
            },
            "path": str(skill.path) if skill.path else None,
            "instructions_preview": skill.instructions[:500] + "..."
            if len(skill.instructions) > 500
            else skill.instructions,
        }


# Singleton instance for convenience
_manager: SkillManager | None = None


def get_skill_manager(project_path: Path | None = None) -> SkillManager:
    """Get the skill manager singleton.

    Args:
        project_path: Optional project path for context.

    Returns:
        SkillManager instance.
    """
    global _manager
    if _manager is None or (project_path and _manager.project_path != project_path):
        _manager = SkillManager(project_path)
    return _manager
