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
        path.mkdir(parents=True, exist_ok=True)

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


def _generate_default_config_yaml() -> str:
    """
    Generate the default configuration YAML with helpful comments.

    Returns:
        YAML string with default configuration.
    """
    return """# InkArms Configuration
# https://github.com/digitalzany/inkarms
#
# This is the global configuration file. Settings here apply to all sessions.
# Use profiles for different contexts (e.g., work, personal, client projects).
# Project-specific settings can be placed in .inkarms/project.yaml

# =============================================================================
# Provider Configuration
# =============================================================================
providers:
  # Default model to use
  default: "anthropic/claude-sonnet-4-20250514"

  # Fallback models if primary fails (in order of preference)
  fallback: []
  #   - "anthropic/claude-3-haiku-20240307"
  #   - "openai/gpt-4o-mini"

  # Model aliases for convenience
  aliases: {}
  #   fast: "anthropic/claude-3-haiku-20240307"
  #   smart: "anthropic/claude-sonnet-4-20250514"
  #   opus: "anthropic/claude-opus-4-20250514"

# =============================================================================
# Context Management
# =============================================================================
context:
  # Percentage of context window before auto-compaction (0.0-1.0)
  auto_compact_threshold: 0.70

  # Percentage of context window before handoff protection triggers
  handoff_threshold: 0.85

  compaction:
    strategy: "summarize"  # summarize, truncate, sliding_window
    preserve_recent_turns: 5

  # Memory storage
  memory_path: "~/.inkarms/memory"
  daily_logs: true

# =============================================================================
# Security & Sandbox
# =============================================================================
security:
  sandbox:
    enable: true
    mode: "whitelist"  # whitelist, blacklist, prompt, disabled

  # Commands allowed in whitelist mode
  whitelist:
    - ls
    - cat
    - head
    - tail
    - grep
    - find
    - echo
    - mkdir
    - cp
    - mv
    - git
    - python
    - pip
    - npm
    - node

  # Commands blocked in blacklist mode
  blacklist:
    - "rm -rf"
    - sudo
    - chmod
    - chown
    - "curl | bash"
    - "wget | bash"
    - dd

  audit_log:
    enable: true
    path: "~/.inkarms/audit.jsonl"
    rotation: "daily"
    retention_days: 90

# =============================================================================
# Skills
# =============================================================================
skills:
  local_path: "~/.inkarms/skills"
  project_path: "./.inkarms/skills"

  smart_index:
    enable: true
    mode: "keyword"  # keyword, llm, off

# =============================================================================
# Cost Management
# =============================================================================
cost:
  budgets:
    daily: null    # Set a number to enable (e.g., 5.00)
    weekly: null
    monthly: null

  alerts:
    warning_threshold: 0.80
    block_on_exceed: false

# =============================================================================
# TUI Settings
# =============================================================================
tui:
  enable: true
  theme: "dark"  # dark, light, auto
  keybindings: "default"  # default, vim, emacs

  chat:
    show_timestamps: true
    show_token_count: true
    show_cost: true
    markdown_rendering: true
    code_highlighting: true

  status_bar:
    show_model: true
    show_context_usage: true
    show_session_cost: true

# =============================================================================
# General Settings
# =============================================================================
general:
  # Default profile to load (null for none)
  default_profile: null

  output:
    format: "rich"  # rich, plain, json
    color: true
    verbose: false

  storage:
    backend: "file"  # file, sqlite
"""


def is_initialized() -> bool:
    """
    Check if InkArms has been initialized.

    Returns:
        True if the home directory and config file exist.
    """
    home = get_inkarms_home()
    config = get_global_config_path()
    return home.exists() and config.exists()


def run_setup(interactive: bool = False, force: bool = False) -> dict[str, Any]:
    """
    Run the first-time setup process.

    Args:
        interactive: If True, prompt user for configuration choices.
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
