"""
Configuration merger for InkArms.

Implements deep merge with special array operations (+/- prefixes).
"""

from typing import Any


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Deep merge two dictionaries with array operation support.

    Merge rules:
    - Scalar values: override replaces base
    - Dicts: recursive deep merge
    - Arrays (default): override replaces base
    - Arrays with '+' prefix key: append to base array
    - Arrays with '-' prefix key: remove items from base array
    - null/None value: remove key from result

    Args:
        base: Base configuration dictionary.
        override: Override configuration dictionary.

    Returns:
        Merged configuration dictionary.

    Examples:
        >>> base = {"whitelist": ["ls", "cat"]}
        >>> override = {"+whitelist": ["git"]}
        >>> deep_merge(base, override)
        {"whitelist": ["ls", "cat", "git"]}

        >>> base = {"whitelist": ["ls", "cat", "git"]}
        >>> override = {"-whitelist": ["git"]}
        >>> deep_merge(base, override)
        {"whitelist": ["ls", "cat"]}
    """
    result = base.copy()

    for key, value in override.items():
        # Handle array append (+prefix)
        if key.startswith("+") and isinstance(value, list):
            actual_key = key[1:]
            if actual_key in result and isinstance(result[actual_key], list):
                # Append unique items
                result[actual_key] = result[actual_key] + [
                    item for item in value if item not in result[actual_key]
                ]
            else:
                result[actual_key] = value

        # Handle array remove (-prefix)
        elif key.startswith("-") and isinstance(value, list):
            actual_key = key[1:]
            if actual_key in result and isinstance(result[actual_key], list):
                result[actual_key] = [item for item in result[actual_key] if item not in value]

        # Handle null (remove key)
        elif value is None:
            result.pop(key, None)

        # Handle nested dict (recursive merge)
        elif isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = deep_merge(result[key], value)

        # Default: replace
        else:
            result[key] = value

    return result


def merge_configs(*configs: dict[str, Any]) -> dict[str, Any]:
    """
    Merge multiple configuration dictionaries in order.

    Later configs override earlier ones.

    Args:
        *configs: Configuration dictionaries to merge.

    Returns:
        Merged configuration dictionary.
    """
    result: dict[str, Any] = {}
    for config in configs:
        if config:
            result = deep_merge(result, config)
    return result


def get_nested_value(config: dict[str, Any], key_path: str) -> Any:
    """
    Get a nested value from a configuration dictionary.

    Args:
        config: Configuration dictionary.
        key_path: Dot-separated key path (e.g., "providers.default").

    Returns:
        The value at the key path, or None if not found.

    Examples:
        >>> config = {"providers": {"default": "gpt-4"}}
        >>> get_nested_value(config, "providers.default")
        "gpt-4"
    """
    keys = key_path.split(".")
    current = config

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None

    return current


def set_nested_value(config: dict[str, Any], key_path: str, value: Any) -> dict[str, Any]:
    """
    Set a nested value in a configuration dictionary.

    Creates intermediate dictionaries as needed.

    Args:
        config: Configuration dictionary.
        key_path: Dot-separated key path (e.g., "providers.default").
        value: Value to set.

    Returns:
        Modified configuration dictionary.

    Examples:
        >>> config = {}
        >>> set_nested_value(config, "providers.default", "gpt-4")
        {"providers": {"default": "gpt-4"}}
    """
    keys = key_path.split(".")
    current = config

    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]

    current[keys[-1]] = value
    return config


def delete_nested_value(config: dict[str, Any], key_path: str) -> dict[str, Any]:
    """
    Delete a nested value from a configuration dictionary.

    Args:
        config: Configuration dictionary.
        key_path: Dot-separated key path (e.g., "providers.default").

    Returns:
        Modified configuration dictionary.
    """
    keys = key_path.split(".")
    current = config

    for key in keys[:-1]:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return config  # Path doesn't exist

    if isinstance(current, dict) and keys[-1] in current:
        del current[keys[-1]]

    return config
