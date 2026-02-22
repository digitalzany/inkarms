"""
First-run setup for InkArms.

Creates the initial directory structure and default configuration files.
"""

import stat
from pathlib import Path
from typing import Any

import yaml

from inkarms.storage.paths import (
    get_cache_dir,
    get_data_dir,
    get_global_config_path,
    get_inkarms_home,
    get_memory_dir,
    get_profiles_dir,
    get_secrets_dir,
    get_skills_dir,
)


def create_directory_structure() -> dict[str, Path]:
    """
    Create the InkArms directory structure.

    Creates:
    - ~/.inkarms/
    - ~/.inkarms/profiles/
    - ~/.inkarms/skills/
    - ~/.inkarms/memory/
    - ~/.inkarms/secrets/ (with restricted permissions)
    - ~/.inkarms/cache/
    - ~/.inkarms/data/ (for metrics and persistent data)

    Returns:
        Dictionary mapping directory names to their paths.
    """
    directories = {
        "home": get_inkarms_home(),
        "profiles": get_profiles_dir(),
        "skills": get_skills_dir(),
        "memory": get_memory_dir(),
        "secrets": get_secrets_dir(),
        "cache": get_cache_dir(),
        "data": get_data_dir(),
    }

    for name, path in directories.items():
        path.mkdir(parents=True, exist_ok=True)  # exist_ok suppresses errors if directory already exists

        # Set restricted permissions on secrets directory (owner only)
        if name == "secrets":
            path.chmod(stat.S_IRWXU)  # 0o700 - owner read/write/execute only

    return directories


def create_default_config(overwrite: bool = False) -> Path | None:
    """
    Create the default global configuration file.

    Args:
        overwrite: If True, overwrite existing config. Default False.

    Returns:
        Path to the created config file, or None if it already exists and overwrite=False.
    """
    config_path = get_global_config_path()

    if config_path.exists() and not overwrite:
        return None

    # Generate default config with comments
    default_config = _generate_default_config_yaml()

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(default_config, encoding="utf-8")

    return config_path


def _get_defaults_dir() -> Path:
    """Return the path to the bundled defaults directory."""
    return Path(__file__).parent / "defaults"


def _generate_default_config_yaml() -> str:
    """
    Load the default configuration YAML from the bundled defaults file.

    Returns:
        YAML string with default configuration.
    """
    default_config_path = _get_defaults_dir() / "default_config.yaml"
    return default_config_path.read_text(encoding="utf-8")


def is_initialized() -> bool:
    """
    Check if InkArms has been initialized.

    Returns:
        True if the home directory and config file exist.
    """
    home = get_inkarms_home()
    config = get_global_config_path()
    return home.exists() and config.exists()


def run_setup(force: bool = False) -> dict[str, Any]:
    """
    Run the first-time setup process.

    Args:
        force: If True, overwrite existing configuration.

    Returns:
        Dictionary with setup results.
    """
    results = {
        "directories": {},
        "config_created": False,
        "config_path": None,
        "already_initialized": False,
    }

    # Check if already initialized
    if is_initialized() and not force:
        results["already_initialized"] = True
        return results

    # Create directory structure
    results["directories"] = create_directory_structure()

    # Create default config
    config_path = create_default_config(overwrite=force)
    if config_path:
        results["config_created"] = True
        results["config_path"] = config_path

    return results


def create_project_config(
    path: Path | None = None,
    overwrite: bool = False,
) -> Path | None:
    """
    Create a project configuration file.

    Args:
        path: Directory to create project config in. Defaults to current directory.
        overwrite: If True, overwrite existing config.

    Returns:
        Path to the created config file, or None if it already exists.
    """
    if path is None:
        path = Path.cwd()

    project_dir = path / ".inkarms"
    config_path = project_dir / "project.yaml"

    if config_path.exists() and not overwrite:
        return None

    project_dir.mkdir(parents=True, exist_ok=True)

    # Generate project config template
    project_config = """# InkArms Project Configuration
# This file contains project-specific settings that override global config.

_meta:
  name: null  # Project name
  description: null  # Project description

# Override provider for this project
# providers:
#   default: "anthropic/claude-sonnet-4-20250514"

# Project-specific skills
skills:
  project_path: "./.inkarms/skills"

# Security overrides (use with caution)
# security:
#   +whitelist:
#     - cargo
#     - rustc
"""

    config_path.write_text(project_config, encoding="utf-8")

    # Also create project skills directory
    skills_dir = project_dir / "skills"
    skills_dir.mkdir(exist_ok=True)

    return config_path


def create_profile(
    name: str,
    description: str | None = None,
    base_config: dict | None = None,
    overwrite: bool = False,
) -> Path | None:
    """
    Create a new profile configuration file.

    Args:
        name: Profile name.
        description: Profile description.
        base_config: Base configuration dictionary to use.
        overwrite: If True, overwrite existing profile.

    Returns:
        Path to the created profile file, or None if it already exists.
    """
    from inkarms.storage.paths import get_profile_path

    profile_path = get_profile_path(name)

    if profile_path.exists() and not overwrite:
        return None

    profile_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate profile config
    profile_content = {
        "_meta": {
            "name": name,
            "description": description,
        }
    }

    if base_config:
        profile_content.update(base_config)

    yaml_content = yaml.dump(
        profile_content,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

    profile_path.write_text(yaml_content, encoding="utf-8")

    return profile_path
