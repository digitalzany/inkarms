"""
Skill parser for InkArms.

Parses skill.yaml and SKILL.md files into skill models.
"""

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from inkarms.skills.models import (
    FilesystemPermissions,
    Skill,
    SkillFrontmatter,
    SkillMetadata,
    SkillPermissions,
)


class SkillParseError(Exception):
    """Error parsing a skill."""

    def __init__(self, message: str, path: Path | None = None):
        self.path = path
        super().__init__(f"{message}" + (f" (at {path})" if path else ""))


class SkillValidationError(SkillParseError):
    """Error validating skill structure or content."""

    pass


def parse_yaml_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
    """Parse YAML frontmatter from a markdown file.

    Frontmatter is delimited by --- at the start and end.

    Args:
        content: The full markdown content.

    Returns:
        Tuple of (frontmatter dict or None, remaining content).
    """
    # Check for frontmatter delimiter
    if not content.startswith("---"):
        return None, content

    # Find the closing delimiter
    lines = content.split("\n")
    end_index = None

    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = i
            break

    if end_index is None:
        # No closing delimiter found
        return None, content

    # Extract and parse frontmatter
    frontmatter_text = "\n".join(lines[1:end_index])
    remaining_content = "\n".join(lines[end_index + 1 :]).strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return None, content
        return frontmatter, remaining_content
    except yaml.YAMLError:
        return None, content


def parse_skill_md(content: str, path: Path | None = None) -> tuple[SkillFrontmatter | None, str]:
    """Parse a SKILL.md file.

    Args:
        content: The SKILL.md file content.
        path: Optional path for error messages.

    Returns:
        Tuple of (frontmatter model or None, instructions content).

    Raises:
        SkillParseError: If the content cannot be parsed.
    """
    frontmatter_dict, instructions = parse_yaml_frontmatter(content)

    if frontmatter_dict is None:
        return None, content.strip()

    try:
        # Validate frontmatter has required fields
        if "name" not in frontmatter_dict:
            raise SkillValidationError("SKILL.md frontmatter missing required 'name' field", path)

        frontmatter = SkillFrontmatter(**frontmatter_dict)
        return frontmatter, instructions
    except ValidationError as e:
        raise SkillParseError(f"Invalid SKILL.md frontmatter: {e}", path)


def parse_skill_yaml(content: str, path: Path | None = None) -> SkillMetadata:
    """Parse a skill.yaml file.

    Args:
        content: The skill.yaml file content.
        path: Optional path for error messages.

    Returns:
        SkillMetadata model.

    Raises:
        SkillParseError: If the content cannot be parsed.
        SkillValidationError: If the content is invalid.
    """
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise SkillParseError(f"Invalid YAML: {e}", path)

    if not isinstance(data, dict):
        raise SkillValidationError("skill.yaml must be a YAML mapping", path)

    # Validate required fields
    if "name" not in data:
        raise SkillValidationError("skill.yaml missing required 'name' field", path)

    # Transform permissions if present
    if "permissions" in data and isinstance(data["permissions"], dict):
        perms = data["permissions"]

        # Handle filesystem permissions
        if "filesystem" in perms and isinstance(perms["filesystem"], dict):
            fs = perms["filesystem"]
            perms["filesystem"] = FilesystemPermissions(
                read=fs.get("read", []),
                write=fs.get("write", []),
            )

        data["permissions"] = SkillPermissions(**perms)

    try:
        return SkillMetadata(**data)
    except ValidationError as e:
        raise SkillValidationError(f"Invalid skill.yaml: {e}", path)


def parse_skill_directory(skill_dir: Path) -> Skill:
    """Parse a skill from a directory.

    A valid skill directory must contain:
    - skill.yaml (required)
    - SKILL.md (required)

    Args:
        skill_dir: Path to the skill directory.

    Returns:
        Fully parsed Skill model.

    Raises:
        SkillParseError: If required files are missing or invalid.
        SkillValidationError: If skill content is invalid.
    """
    skill_dir = Path(skill_dir).resolve()

    if not skill_dir.exists():
        raise SkillParseError(f"Skill directory does not exist: {skill_dir}")

    if not skill_dir.is_dir():
        raise SkillParseError(f"Not a directory: {skill_dir}")

    # Check for required files
    skill_yaml_path = skill_dir / "skill.yaml"
    skill_md_path = skill_dir / "SKILL.md"

    if not skill_yaml_path.exists():
        raise SkillParseError(f"Missing required file: skill.yaml", skill_dir)

    if not skill_md_path.exists():
        raise SkillParseError(f"Missing required file: SKILL.md", skill_dir)

    # Parse skill.yaml
    try:
        skill_yaml_content = skill_yaml_path.read_text()
    except OSError as e:
        raise SkillParseError(f"Failed to read skill.yaml: {e}", skill_yaml_path)

    metadata = parse_skill_yaml(skill_yaml_content, skill_yaml_path)

    # Parse SKILL.md
    try:
        skill_md_content = skill_md_path.read_text()
    except OSError as e:
        raise SkillParseError(f"Failed to read SKILL.md: {e}", skill_md_path)

    frontmatter, instructions = parse_skill_md(skill_md_content, skill_md_path)

    # Validate name consistency if frontmatter present
    if frontmatter and frontmatter.name != metadata.name:
        raise SkillValidationError(
            f"Name mismatch: skill.yaml has '{metadata.name}', SKILL.md has '{frontmatter.name}'",
            skill_dir,
        )

    # Use description from SKILL.md frontmatter if not in skill.yaml
    if frontmatter and frontmatter.description and not metadata.description:
        metadata.description = frontmatter.description

    return Skill(
        metadata=metadata,
        instructions=instructions,
        path=skill_dir,
    )


def validate_skill_directory(skill_dir: Path) -> list[str]:
    """Validate a skill directory and return any issues.

    This performs a full validation including:
    - Required files exist
    - YAML is valid
    - Names match
    - All required fields present

    Args:
        skill_dir: Path to the skill directory.

    Returns:
        List of validation issues (empty if valid).
    """
    issues: list[str] = []
    skill_dir = Path(skill_dir).resolve()

    # Check directory exists
    if not skill_dir.exists():
        issues.append(f"Directory does not exist: {skill_dir}")
        return issues

    if not skill_dir.is_dir():
        issues.append(f"Not a directory: {skill_dir}")
        return issues

    # Check required files
    skill_yaml_path = skill_dir / "skill.yaml"
    skill_md_path = skill_dir / "SKILL.md"

    if not skill_yaml_path.exists():
        issues.append("Missing required file: skill.yaml")
    if not skill_md_path.exists():
        issues.append("Missing required file: SKILL.md")

    if issues:
        return issues

    # Parse and validate skill.yaml
    try:
        skill_yaml_content = skill_yaml_path.read_text()
        metadata = parse_skill_yaml(skill_yaml_content, skill_yaml_path)
    except (SkillParseError, SkillValidationError) as e:
        issues.append(f"skill.yaml: {e}")
        metadata = None

    # Parse and validate SKILL.md
    try:
        skill_md_content = skill_md_path.read_text()
        frontmatter, instructions = parse_skill_md(skill_md_content, skill_md_path)
    except (SkillParseError, SkillValidationError) as e:
        issues.append(f"SKILL.md: {e}")
        frontmatter = None
        instructions = ""

    # Check name consistency
    if metadata and frontmatter:
        if frontmatter.name != metadata.name:
            issues.append(
                f"Name mismatch: skill.yaml has '{metadata.name}', "
                f"SKILL.md has '{frontmatter.name}'"
            )

    # Check for empty instructions
    if not instructions.strip():
        issues.append("SKILL.md has no instructions content")

    # Warn about missing but recommended fields
    if metadata:
        if not metadata.description:
            issues.append("Warning: No description provided")
        if not metadata.keywords:
            issues.append("Warning: No keywords provided (skill won't be discoverable)")
        if not metadata.version or metadata.version == "1.0.0":
            # Version is fine, but note if using default
            pass

    return issues
