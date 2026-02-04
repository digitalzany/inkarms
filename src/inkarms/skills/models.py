"""
Skill models for InkArms.

Defines the data structures for skills, including metadata, permissions,
and the skill content itself.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class FilesystemPermissions(BaseModel):
    """Filesystem access permissions for a skill."""

    read: list[str] = Field(default_factory=list, description="Glob patterns for readable files")
    write: list[str] = Field(default_factory=list, description="Glob patterns for writable files")


class SkillPermissions(BaseModel):
    """Permission declarations for a skill.

    Skills must declare what tools and resources they need access to.
    InkArms enforces these permissions at runtime.
    """

    tools: list[str] = Field(
        default_factory=list,
        description="Tools the skill is allowed to use (e.g., bash, file_read, file_write)",
    )
    network: bool = Field(
        default=False,
        description="Whether the skill needs network access",
    )
    filesystem: FilesystemPermissions = Field(
        default_factory=FilesystemPermissions,
        description="Filesystem access permissions",
    )

    @classmethod
    def default_readonly(cls) -> "SkillPermissions":
        """Create default read-only permissions."""
        return cls(
            tools=["file_read"],
            network=False,
            filesystem=FilesystemPermissions(read=["*"], write=[]),
        )


class SkillMetadata(BaseModel):
    """Metadata from skill.yaml.

    Contains all the metadata needed to identify, discover, and
    manage a skill.
    """

    name: str = Field(..., description="Unique skill identifier")
    version: str = Field(default="1.0.0", description="Semantic version")
    description: str = Field(default="", description="Short description of what the skill does")

    # Discovery metadata
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords for skill discovery",
    )

    # Authorship
    author: str | None = Field(default=None, description="Skill author")
    license: str | None = Field(default=None, description="License (e.g., MIT)")
    repository: str | None = Field(default=None, description="Source repository URL")

    # Permissions
    permissions: SkillPermissions = Field(
        default_factory=SkillPermissions,
        description="Permission declarations",
    )

    # Dependencies (for future use)
    dependencies: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Dependencies (skills, packages)",
    )

    # Compatibility
    compatible_with: list[str] = Field(
        default_factory=lambda: ["inkarms"],
        description="Compatible AI agents/tools",
    )


class SkillFrontmatter(BaseModel):
    """Frontmatter parsed from SKILL.md.

    The SKILL.md file can have YAML frontmatter with basic metadata.
    This is a subset of SkillMetadata for convenience.
    """

    name: str = Field(..., description="Skill name (must match skill.yaml)")
    description: str = Field(default="", description="Short description")


class Skill(BaseModel):
    """A complete skill with metadata and instructions.

    This represents a fully loaded skill ready for use.
    """

    metadata: SkillMetadata = Field(..., description="Skill metadata from skill.yaml")
    instructions: str = Field(..., description="Instructions content from SKILL.md")
    path: Path | None = Field(default=None, description="Path to the skill directory")

    # Computed/cached fields
    loaded_at: datetime = Field(
        default_factory=datetime.now,
        description="When the skill was loaded",
    )

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True

    @property
    def name(self) -> str:
        """Get the skill name."""
        return self.metadata.name

    @property
    def keywords(self) -> list[str]:
        """Get the skill keywords."""
        return self.metadata.keywords

    @property
    def permissions(self) -> SkillPermissions:
        """Get the skill permissions."""
        return self.metadata.permissions

    def get_system_prompt_injection(self) -> str:
        """Get the content to inject into the system prompt.

        Returns:
            The skill instructions formatted for system prompt injection.
        """
        return f"""## Skill: {self.metadata.name}

{self.metadata.description}

{self.instructions}
"""


class SkillIndexEntry(BaseModel):
    """An entry in the skill index.

    Used for efficient skill discovery without loading full skills.
    """

    name: str = Field(..., description="Skill name")
    version: str = Field(default="1.0.0", description="Skill version")
    description: str = Field(default="", description="Short description")
    keywords: list[str] = Field(default_factory=list, description="Keywords for discovery")
    path: str = Field(..., description="Path to the skill directory")
    is_global: bool = Field(default=True, description="Whether this is a global skill")
    indexed_at: datetime = Field(
        default_factory=datetime.now,
        description="When this entry was indexed",
    )


class SkillIndex(BaseModel):
    """The skill index for fast discovery.

    Stored at ~/.inkarms/skills/index.json
    """

    version: str = Field(default="1.0.0", description="Index format version")
    skills: dict[str, SkillIndexEntry] = Field(
        default_factory=dict,
        description="Map of skill name to index entry",
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="Last update timestamp",
    )

    def add_skill(self, entry: SkillIndexEntry) -> None:
        """Add or update a skill in the index."""
        self.skills[entry.name] = entry
        self.updated_at = datetime.now()

    def remove_skill(self, name: str) -> bool:
        """Remove a skill from the index.

        Returns:
            True if the skill was removed, False if not found.
        """
        if name in self.skills:
            del self.skills[name]
            self.updated_at = datetime.now()
            return True
        return False

    def search(self, query: str, max_results: int = 5) -> list[SkillIndexEntry]:
        """Search skills by keyword matching.

        Args:
            query: Search query (matched against name, description, keywords)
            max_results: Maximum number of results to return

        Returns:
            List of matching skills, sorted by relevance.
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())
        scored_skills: list[tuple[int, SkillIndexEntry]] = []

        for entry in self.skills.values():
            score = 0

            # Exact name match (highest priority)
            if entry.name.lower() == query_lower:
                score += 100

            # Name contains query
            if query_lower in entry.name.lower():
                score += 50

            # Keyword matches
            entry_keywords_lower = [k.lower() for k in entry.keywords]
            for keyword in entry_keywords_lower:
                if query_lower == keyword:
                    score += 30
                elif query_lower in keyword or keyword in query_lower:
                    score += 15
                # Check individual words
                for word in query_words:
                    if word in keyword:
                        score += 5

            # Description matches
            if query_lower in entry.description.lower():
                score += 10
            for word in query_words:
                if word in entry.description.lower():
                    score += 3

            if score > 0:
                scored_skills.append((score, entry))

        # Sort by score (descending) and return top results
        scored_skills.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored_skills[:max_results]]

    def list_all(self) -> list[SkillIndexEntry]:
        """List all skills in the index.

        Returns:
            List of all skill entries.
        """
        return list(self.skills.values())
