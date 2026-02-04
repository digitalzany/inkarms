"""
Path utilities for InkArms.

Provides consistent path resolution for configuration, data, and cache files.
"""

import os
from pathlib import Path


def get_inkarms_home() -> Path:
    """
    Get the InkArms home directory.

    Resolution order:
    1. INKARMS_HOME environment variable
    2. Default: ~/.inkarms

    Returns:
        Path to the InkArms home directory.
    """
    env_home = os.environ.get("INKARMS_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return Path.home() / ".inkarms"


def get_global_config_path() -> Path:
    """
    Get the path to the global configuration file.

    Returns:
        Path to ~/.inkarms/config.yaml
    """
    return get_inkarms_home() / "config.yaml"


def get_profiles_dir() -> Path:
    """
    Get the profiles directory.

    Returns:
        Path to ~/.inkarms/profiles/
    """
    return get_inkarms_home() / "profiles"


def get_profile_path(profile_name: str) -> Path:
    """
    Get the path to a specific profile configuration file.

    Args:
        profile_name: Name of the profile.

    Returns:
        Path to ~/.inkarms/profiles/<name>.yaml
    """
    return get_profiles_dir() / f"{profile_name}.yaml"


def get_skills_dir() -> Path:
    """
    Get the global skills directory.

    Returns:
        Path to ~/.inkarms/skills/
    """
    return get_inkarms_home() / "skills"


def get_memory_dir() -> Path:
    """
    Get the memory directory.

    Returns:
        Path to ~/.inkarms/memory/
    """
    return get_inkarms_home() / "memory"


def get_secrets_dir() -> Path:
    """
    Get the secrets directory.

    Returns:
        Path to ~/.inkarms/secrets/
    """
    return get_inkarms_home() / "secrets"


def get_cache_dir() -> Path:
    """
    Get the cache directory.

    Returns:
        Path to ~/.inkarms/cache/
    """
    return get_inkarms_home() / "cache"


def get_data_dir() -> Path:
    """
    Get the data directory for tool metrics and other persistent data.

    Returns:
        Path to ~/.inkarms/data/
    """
    return get_inkarms_home() / "data"


def get_audit_log_path() -> Path:
    """
    Get the default audit log path.

    Returns:
        Path to ~/.inkarms/audit.jsonl
    """
    return get_inkarms_home() / "audit.jsonl"


def get_sqlite_db_path() -> Path:
    """
    Get the SQLite database path.

    Returns:
        Path to ~/.inkarms/data.db
    """
    return get_inkarms_home() / "data.db"


def find_project_config(start_path: Path | None = None) -> Path | None:
    """
    Find the project configuration file by traversing up the directory tree.

    Looks for .inkarms/project.yaml starting from the given path
    (or current directory) and moving up to the root.

    Args:
        start_path: Starting directory to search from. Defaults to cwd.

    Returns:
        Path to the project config if found, None otherwise.
    """
    if start_path is None:
        start_path = Path.cwd()
    else:
        start_path = Path(start_path).resolve()

    current = start_path
    while current != current.parent:
        project_config = current / ".inkarms" / "project.yaml"
        if project_config.exists():
            return project_config
        current = current.parent

    # Check root as well
    project_config = current / ".inkarms" / "project.yaml"
    if project_config.exists():
        return project_config

    return None


def get_project_inkarms_dir(start_path: Path | None = None) -> Path | None:
    """
    Find the project's .inkarms directory.

    Args:
        start_path: Starting directory to search from. Defaults to cwd.

    Returns:
        Path to the .inkarms directory if found, None otherwise.
    """
    config_path = find_project_config(start_path)
    if config_path:
        return config_path.parent
    return None


def expand_path(path: str | Path) -> Path:
    """
    Expand a path string, handling ~ and environment variables.

    Args:
        path: Path string or Path object.

    Returns:
        Expanded and resolved Path.
    """
    if isinstance(path, str):
        # Expand environment variables
        path = os.path.expandvars(path)
        # Expand user home
        path = os.path.expanduser(path)
    return Path(path).resolve()


def ensure_directory(path: Path, mode: int = 0o755) -> Path:
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path.
        mode: Permission mode for created directories.

    Returns:
        The path (for chaining).
    """
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    return path


def list_profiles() -> list[str]:
    """
    List all available profile names.

    Returns:
        List of profile names (without .yaml extension).
    """
    profiles_dir = get_profiles_dir()
    if not profiles_dir.exists():
        return []

    return [
        p.stem for p in profiles_dir.glob("*.yaml") if p.is_file() and not p.name.startswith(".")
    ]
