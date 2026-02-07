"""
Configuration loader for InkArms.

Loads and merges configuration from multiple sources:
1. Default values
2. Global config (~/.inkarms/config.yaml)
3. Profile config (~/.inkarms/profiles/<name>.yaml)
4. Project config (./.inkarms/project.yaml)
5. Environment variables (INKARMS_*)
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml

from inkarms.config.merger import deep_merge, get_nested_value, merge_configs, set_nested_value
from inkarms.config.schema import Config
from inkarms.storage.paths import (
    find_project_config,
    get_global_config_path,
    get_profile_path,
)


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""

    pass


def load_yaml_file(path: Path) -> dict[str, Any]:
    """
    Load a YAML configuration file.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed configuration dictionary.

    Raises:
        ConfigurationError: If the file cannot be read or parsed.
    """
    try:
        with open(path, encoding="utf-8") as f:
            content = yaml.safe_load(f)
            return content if content else {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML in {path}: {e}") from e
    except OSError as e:
        raise ConfigurationError(f"Cannot read {path}: {e}") from e


def save_yaml_file(path: Path, config: dict[str, Any]) -> None:
    """
    Save a configuration dictionary to a YAML file.

    Args:
        path: Path to the YAML file.
        config: Configuration dictionary to save.

    Raises:
        ConfigurationError: If the file cannot be written.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    except OSError as e:
        raise ConfigurationError(f"Cannot write {path}: {e}") from e


def apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """
    Apply environment variable overrides to configuration.

    Environment variables follow the pattern:
    INKARMS_<SECTION>_<KEY>=<value>
    INKARMS_<SECTION>_<NESTED>_<KEY>=<value>

    Args:
        config: Configuration dictionary to modify.

    Returns:
        Configuration with environment overrides applied.
    """
    prefix = "INKARMS_"

    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue

        # Skip INKARMS_HOME as it's handled separately
        if key == "INKARMS_HOME":
            continue

        # Convert INKARMS_PROVIDERS_DEFAULT to providers.default
        config_key = key[len(prefix) :].lower().replace("_", ".")

        # Parse value type
        parsed_value = _parse_env_value(value)

        # Set the nested value
        config = set_nested_value(config, config_key, parsed_value)

    return config


def _parse_env_value(value: str) -> Any:
    """
    Parse an environment variable value to the appropriate type.

    Args:
        value: String value from environment.

    Returns:
        Parsed value (bool, int, float, or string).
    """
    # Boolean
    if value.lower() in ("true", "yes", "1", "on"):
        return True
    if value.lower() in ("false", "no", "0", "off"):
        return False

    # Integer
    if re.match(r"^-?\d+$", value):
        return int(value)

    # Float
    if re.match(r"^-?\d+\.\d+$", value):
        return float(value)

    # List (comma-separated)
    if "," in value:
        return [item.strip() for item in value.split(",")]

    # String
    return value


def load_config(
    profile: str | None = None,
    project_path: Path | None = None,
    skip_project: bool = False,
    skip_env: bool = False,
) -> Config:
    """
    Load and merge configuration from all sources.

    Loading order (later overrides earlier):
    1. Default values from Config model
    2. Global config (~/.inkarms/config.yaml)
    3. Profile config (~/.inkarms/profiles/<name>.yaml) if specified
    4. Project config (./.inkarms/project.yaml) if found
    5. Environment variables (INKARMS_*)

    Args:
        profile: Profile name to load. Can also be set via INKARMS_PROFILE env var.
        project_path: Starting path to search for project config. Defaults to cwd.
        skip_project: Skip loading project configuration.
        skip_env: Skip environment variable overrides.

    Returns:
        Merged and validated Config object.

    Raises:
        ConfigurationError: If configuration is invalid.
    """
    # 1. Start with defaults
    config_dict = Config().model_dump()

    # 2. Load global config
    global_path = get_global_config_path()
    if global_path.exists():
        global_config = load_yaml_file(global_path)
        config_dict = deep_merge(config_dict, global_config)

    # 3. Determine profile to load
    profile_name = profile or os.environ.get("INKARMS_PROFILE")
    if not profile_name:
        # Check if default_profile is set in global config
        profile_name = get_nested_value(config_dict, "general.default_profile")

    # 4. Load profile config
    if profile_name:
        profile_path = get_profile_path(profile_name)
        if profile_path.exists():
            profile_config = load_yaml_file(profile_path)
            # Remove _meta from profile config before merging
            profile_config.pop("_meta", None)
            config_dict = deep_merge(config_dict, profile_config)

    # 5. Load project config
    if not skip_project:
        project_config_path = find_project_config(project_path)
        if project_config_path and project_config_path.exists():
            project_config = load_yaml_file(project_config_path)
            # Remove _meta from project config before merging
            project_config.pop("_meta", None)
            config_dict = deep_merge(config_dict, project_config)

    # 6. Apply environment variables
    if not skip_env:
        config_dict = apply_env_overrides(config_dict)

    # 7. Validate and return
    try:
        return Config.model_validate(config_dict)

    except Exception as e:
        raise ConfigurationError(f"Configuration validation failed: {e}") from e


def get_config_sources() -> dict[str, Path | None]:
    """
    Get paths to all configuration sources.

    Returns:
        Dictionary mapping source names to paths (None if not found).
    """
    global_path = get_global_config_path()
    project_path = find_project_config()

    # Get profile name from env or global config
    profile_name = os.environ.get("INKARMS_PROFILE")
    if not profile_name and global_path.exists():
        global_config = load_yaml_file(global_path)
        profile_name = get_nested_value(global_config, "general.default_profile")

    profile_path = get_profile_path(profile_name) if profile_name else None

    return {
        "global": global_path if global_path.exists() else None,
        "profile": profile_path if profile_path and profile_path.exists() else None,
        "project": project_path if project_path and project_path.exists() else None,
    }


# Singleton for cached config
_cached_config: Config | None = None


def get_config(reload: bool = False) -> Config:
    """
    Get the global configuration instance.

    Uses a cached instance for performance. Use reload=True to force refresh.

    Args:
        reload: Force reload configuration from disk.

    Returns:
        Config instance.
    """
    global _cached_config

    if _cached_config is None or reload:
        _cached_config = load_config()

    return _cached_config


def clear_config_cache() -> None:
    """Clear the cached configuration."""
    global _cached_config
    _cached_config = None
