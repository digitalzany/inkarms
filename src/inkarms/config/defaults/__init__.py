"""
Default configuration loader.

Loads and caches the bundled default configuration from default_config.yaml.
This is the single source of truth for all default values.
"""

from pathlib import Path
from typing import Any

import yaml

_CACHED_DEFAULTS: dict[str, Any] | None = None


def _get_defaults_dir() -> Path:
    """Return the path to the bundled defaults directory."""
    return Path(__file__).parent


def get_default_config() -> dict[str, Any]:
    """
    Load and cache the full default configuration.

    Returns:
        Parsed default configuration dictionary.
    """
    global _CACHED_DEFAULTS
    if _CACHED_DEFAULTS is None:
        config_path = _get_defaults_dir() / "default_config.yaml"
        with open(config_path, encoding="utf-8") as f:
            _CACHED_DEFAULTS = yaml.safe_load(f) or {}
    return _CACHED_DEFAULTS


def get_security_defaults() -> dict[str, Any]:
    """Get the security section defaults."""
    return get_default_config().get("security", {})
