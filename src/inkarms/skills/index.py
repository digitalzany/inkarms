"""
Skill index for InkArms.

Provides fast keyword-based skill discovery through an index file.
"""

import json
from datetime import datetime
from pathlib import Path

from inkarms.skills.loader import (
    discover_all_skills,
    get_global_skills_dir,
)
from inkarms.skills.models import SkillIndex, SkillIndexEntry
from inkarms.skills.parser import (
    SkillParseError,
    SkillValidationError,
    parse_skill_directory,
)


def get_index_path() -> Path:
    """Get the path to the skill index file.

    Returns:
        Path to ~/.inkarms/skills/index.json
    """
    return get_global_skills_dir() / "index.json"


def load_index() -> SkillIndex:
    """Load the skill index from disk.

    Returns:
        SkillIndex (empty if file doesn't exist or is invalid).
    """
    index_path = get_index_path()

    if not index_path.exists():
        return SkillIndex()

    try:
        content = index_path.read_text()
        data = json.loads(content)

        # Parse skill entries
        skills = {}
        for name, entry_data in data.get("skills", {}).items():
            # Handle datetime fields
            if "indexed_at" in entry_data and isinstance(entry_data["indexed_at"], str):
                entry_data["indexed_at"] = datetime.fromisoformat(entry_data["indexed_at"])
            skills[name] = SkillIndexEntry(**entry_data)

        # Handle updated_at
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        else:
            updated_at = datetime.now()

        return SkillIndex(
            version=data.get("version", "1.0.0"),
            skills=skills,
            updated_at=updated_at,
        )

    except (json.JSONDecodeError, KeyError, ValueError):
        # Return empty index on any parse error
        return SkillIndex()


def save_index(index: SkillIndex) -> None:
    """Save the skill index to disk.

    Args:
        index: The index to save.
    """
    index_path = get_index_path()

    # Ensure directory exists
    index_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to JSON-serializable dict
    data = {
        "version": index.version,
        "updated_at": index.updated_at.isoformat(),
        "skills": {},
    }

    for name, entry in index.skills.items():
        data["skills"][name] = {
            "name": entry.name,
            "version": entry.version,
            "description": entry.description,
            "keywords": entry.keywords,
            "path": entry.path,
            "is_global": entry.is_global,
            "indexed_at": entry.indexed_at.isoformat(),
        }

    index_path.write_text(json.dumps(data, indent=2))


def rebuild_index(include_project: bool = True) -> SkillIndex:
    """Rebuild the skill index from scratch.

    Scans all skill directories and creates a fresh index.

    Args:
        include_project: Whether to include project-level skills.

    Returns:
        The rebuilt index.
    """
    index = SkillIndex()

    # Discover all skills
    all_skills = discover_all_skills(include_project)

    for skill_path, is_global in all_skills:
        try:
            skill = parse_skill_directory(skill_path)

            entry = SkillIndexEntry(
                name=skill.name,
                version=skill.metadata.version,
                description=skill.metadata.description,
                keywords=skill.metadata.keywords,
                path=str(skill_path),
                is_global=is_global,
            )
            index.add_skill(entry)

        except (SkillParseError, SkillValidationError):
            # Skip invalid skills
            continue

    # Save the rebuilt index
    save_index(index)

    return index


def update_index_entry(skill_path: Path, is_global: bool = True) -> SkillIndex:
    """Update or add a single skill to the index.

    Args:
        skill_path: Path to the skill directory.
        is_global: Whether this is a global skill.

    Returns:
        The updated index.

    Raises:
        SkillParseError: If the skill cannot be parsed.
    """
    index = load_index()

    skill = parse_skill_directory(skill_path)

    entry = SkillIndexEntry(
        name=skill.name,
        version=skill.metadata.version,
        description=skill.metadata.description,
        keywords=skill.metadata.keywords,
        path=str(skill_path),
        is_global=is_global,
    )
    index.add_skill(entry)

    save_index(index)

    return index


def remove_from_index(name: str) -> bool:
    """Remove a skill from the index.

    Args:
        name: Skill name to remove.

    Returns:
        True if removed, False if not found.
    """
    index = load_index()

    if index.remove_skill(name):
        save_index(index)
        return True

    return False


def search_skills(query: str, max_results: int = 5) -> list[SkillIndexEntry]:
    """Search for skills by keyword.

    Args:
        query: Search query.
        max_results: Maximum number of results.

    Returns:
        List of matching skill entries.
    """
    index = load_index()
    return index.search(query, max_results)


def get_skills_for_query(query: str, max_skills: int = 3) -> list[SkillIndexEntry]:
    """Get relevant skills for a user query.

    This is the main entry point for automatic skill discovery.
    It uses keyword matching to find skills relevant to the query.

    Args:
        query: User's query/prompt.
        max_skills: Maximum number of skills to return.

    Returns:
        List of relevant skill entries.
    """
    # Split query into words for better matching
    words = query.lower().split()

    # Search for each significant word (skip common words)
    common_words = {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "up",
        "about",
        "into",
        "over",
        "after",
        "beneath",
        "under",
        "above",
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "me",
        "him",
        "her",
        "us",
        "them",
        "my",
        "your",
        "his",
        "its",
        "our",
        "their",
        "this",
        "that",
        "these",
        "those",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "where",
        "when",
        "why",
        "how",
        "and",
        "but",
        "or",
        "nor",
        "so",
        "yet",
        "both",
        "either",
        "neither",
        "not",
        "only",
        "just",
        "also",
        "please",
        "help",
    }

    significant_words = [w for w in words if w not in common_words and len(w) > 2]

    # Use the full query for best results
    results = search_skills(query, max_skills * 2)

    # Also search significant individual words and combine
    for word in significant_words[:5]:  # Limit to first 5 significant words
        word_results = search_skills(word, max_skills)
        for entry in word_results:
            if entry not in results:
                results.append(entry)

    # Deduplicate and return top results
    seen = set()
    unique_results = []
    for entry in results:
        if entry.name not in seen:
            seen.add(entry.name)
            unique_results.append(entry)

    return unique_results[:max_skills]
