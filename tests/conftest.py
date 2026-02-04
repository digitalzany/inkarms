"""
Pytest configuration and fixtures for inkarms tests.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_inkarms_home(temp_dir: Path) -> Generator[Path, None, None]:
    """Provide a mock ~/.inkarms directory."""
    inkarms_home = temp_dir / ".inkarms"
    inkarms_home.mkdir()

    # Create subdirectories
    (inkarms_home / "profiles").mkdir()
    (inkarms_home / "skills").mkdir()
    (inkarms_home / "memory").mkdir()
    (inkarms_home / "secrets").mkdir()
    (inkarms_home / "cache").mkdir()

    yield inkarms_home


@pytest.fixture
def mock_project_dir(temp_dir: Path) -> Generator[Path, None, None]:
    """Provide a mock project directory with .inkarms/ config."""
    project_dir = temp_dir / "test-project"
    project_dir.mkdir()

    inkarms_dir = project_dir / ".inkarms"
    inkarms_dir.mkdir()
    (inkarms_dir / "skills").mkdir()

    yield project_dir


@pytest.fixture
def sample_config() -> dict:
    """Provide a sample configuration dictionary."""
    return {
        "providers": {
            "default": "anthropic/claude-sonnet-4.5",
            "fallback": ["openai/gpt-4"],
            "aliases": {
                "fast": "openai/gpt-3.5-turbo",
                "smart": "anthropic/claude-opus-4.5",
            },
        },
        "security": {
            "sandbox": {
                "enable": True,
                "mode": "whitelist",
            },
            "whitelist": ["ls", "cat", "git", "python"],
        },
        "skills": {
            "local_path": "~/.inkarms/skills",
            "smart_index": {
                "enable": True,
                "mode": "keyword",
            },
        },
    }


@pytest.fixture
def sample_skill_yaml() -> str:
    """Provide sample skill.yaml content."""
    return """
name: test-skill
version: 1.0.0
description: A test skill for unit tests

keywords:
  - test
  - example

permissions:
  tools:
    - file_read
  network: false
  filesystem:
    read:
      - "*.py"
    write: []
"""


@pytest.fixture
def sample_skill_md() -> str:
    """Provide sample SKILL.md content."""
    return """---
name: test-skill
description: A test skill for unit tests
---

# Test Skill

This is a test skill for unit testing.

## Instructions

1. Do something
2. Do something else

## Output Format

Return results in a specific format.
"""
