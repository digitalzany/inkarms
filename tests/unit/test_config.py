"""
Unit tests for the InkArms configuration system.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from inkarms.config import (
    Config,
    ConfigurationError,
    deep_merge,
    delete_nested_value,
    get_nested_value,
    load_config,
    load_config_dict,
    load_yaml_file,
    merge_configs,
    save_yaml_file,
    set_nested_value,
)
from inkarms.config.setup import (
    create_default_config,
    create_directory_structure,
    create_profile,
    create_project_config,
    is_initialized,
    run_setup,
)
from inkarms.storage.paths import (
    get_global_config_path,
    get_inkarms_home,
    get_profile_path,
)


# =============================================================================
# Schema Tests
# =============================================================================


class TestConfigSchema:
    """Tests for the Config Pydantic schema."""

    def test_default_config_is_valid(self):
        """Test that the default Config() is valid."""
        config = Config()
        assert config.providers.default == "anthropic/claude-sonnet-4-20250514"
        assert config.security.sandbox.enable is True
        assert config.tui.enable is True

    def test_config_from_dict(self, sample_config):
        """Test Config validation from a dictionary."""
        config = Config.model_validate(sample_config)
        assert config.providers.default == "anthropic/claude-sonnet-4.5"
        assert config.security.whitelist == ["ls", "cat", "git", "python"]

    def test_config_with_invalid_values(self):
        """Test that invalid configuration values are rejected."""
        invalid_config = {
            "context": {
                "auto_compact_threshold": 2.0,  # Must be 0.0-1.0
            }
        }
        with pytest.raises(Exception):  # Pydantic ValidationError
            Config.model_validate(invalid_config)

    def test_get_default_model(self):
        """Test the get_default_model helper."""
        config = Config()
        assert config.get_default_model() == "anthropic/claude-sonnet-4-20250514"

    def test_resolve_model_alias(self):
        """Test model alias resolution."""
        config = Config.model_validate(
            {
                "providers": {
                    "default": "fast",
                    "aliases": {
                        "fast": "openai/gpt-3.5-turbo",
                        "smart": "anthropic/claude-opus-4",
                    },
                }
            }
        )
        assert config.resolve_model_alias("fast") == "openai/gpt-3.5-turbo"
        assert config.resolve_model_alias("smart") == "anthropic/claude-opus-4"
        assert config.resolve_model_alias("unknown") == "unknown"

    def test_is_sandbox_enabled(self):
        """Test sandbox enabled check."""
        # Default: enabled
        config = Config()
        assert config.is_sandbox_enabled() is True

        # Disabled via mode
        config = Config.model_validate(
            {"security": {"sandbox": {"enable": True, "mode": "disabled"}}}
        )
        assert config.is_sandbox_enabled() is False

        # Disabled via enable
        config = Config.model_validate(
            {"security": {"sandbox": {"enable": False, "mode": "whitelist"}}}
        )
        assert config.is_sandbox_enabled() is False


# =============================================================================
# Merger Tests
# =============================================================================


class TestDeepMerge:
    """Tests for the deep_merge function."""

    def test_basic_merge(self):
        """Test basic dictionary merge."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        """Test nested dictionary merge."""
        base = {"a": {"b": 1, "c": 2}}
        override = {"a": {"c": 3, "d": 4}}
        result = deep_merge(base, override)
        assert result == {"a": {"b": 1, "c": 3, "d": 4}}

    def test_array_replace(self):
        """Test that arrays are replaced by default."""
        base = {"list": [1, 2, 3]}
        override = {"list": [4, 5]}
        result = deep_merge(base, override)
        assert result == {"list": [4, 5]}

    def test_array_append_with_plus_prefix(self):
        """Test array append with + prefix."""
        base = {"whitelist": ["ls", "cat"]}
        override = {"+whitelist": ["git", "python"]}
        result = deep_merge(base, override)
        assert result == {"whitelist": ["ls", "cat", "git", "python"]}

    def test_array_append_unique_only(self):
        """Test that array append only adds unique items."""
        base = {"whitelist": ["ls", "cat", "git"]}
        override = {"+whitelist": ["git", "python"]}  # git already exists
        result = deep_merge(base, override)
        assert result == {"whitelist": ["ls", "cat", "git", "python"]}

    def test_array_remove_with_minus_prefix(self):
        """Test array remove with - prefix."""
        base = {"whitelist": ["ls", "cat", "git", "sudo"]}
        override = {"-whitelist": ["sudo", "git"]}
        result = deep_merge(base, override)
        assert result == {"whitelist": ["ls", "cat"]}

    def test_null_removes_key(self):
        """Test that null value removes the key."""
        base = {"a": 1, "b": 2, "c": 3}
        override = {"b": None}
        result = deep_merge(base, override)
        assert result == {"a": 1, "c": 3}

    def test_merge_configs_multiple(self):
        """Test merging multiple configs in order."""
        config1 = {"a": 1}
        config2 = {"b": 2}
        config3 = {"a": 3, "c": 3}
        result = merge_configs(config1, config2, config3)
        assert result == {"a": 3, "b": 2, "c": 3}


class TestNestedValue:
    """Tests for get/set/delete nested value functions."""

    def test_get_nested_value(self):
        """Test getting nested values."""
        config = {"a": {"b": {"c": 42}}}
        assert get_nested_value(config, "a.b.c") == 42
        assert get_nested_value(config, "a.b") == {"c": 42}
        assert get_nested_value(config, "a.b.d") is None
        assert get_nested_value(config, "x.y.z") is None

    def test_set_nested_value(self):
        """Test setting nested values."""
        config = {}
        result = set_nested_value(config, "a.b.c", 42)
        assert result == {"a": {"b": {"c": 42}}}

        config = {"a": {"b": 1}}
        result = set_nested_value(config, "a.c", 2)
        assert result == {"a": {"b": 1, "c": 2}}

    def test_delete_nested_value(self):
        """Test deleting nested values."""
        config = {"a": {"b": {"c": 42, "d": 43}}}
        result = delete_nested_value(config, "a.b.c")
        assert result == {"a": {"b": {"d": 43}}}

        # Non-existent key does nothing
        result = delete_nested_value(config, "x.y.z")
        assert result == {"a": {"b": {"d": 43}}}


# =============================================================================
# Loader Tests
# =============================================================================


class TestConfigLoader:
    """Tests for the configuration loader."""

    def test_load_yaml_file(self, temp_dir):
        """Test loading a YAML file."""
        config_file = temp_dir / "test.yaml"
        config_file.write_text("providers:\n  default: 'test-model'\n")

        result = load_yaml_file(config_file)
        assert result == {"providers": {"default": "test-model"}}

    def test_load_yaml_file_not_found(self, temp_dir):
        """Test loading a non-existent YAML file returns empty dict."""
        config_file = temp_dir / "nonexistent.yaml"
        result = load_yaml_file(config_file)
        assert result == {}

    def test_load_yaml_file_invalid(self, temp_dir):
        """Test loading invalid YAML raises error."""
        config_file = temp_dir / "invalid.yaml"
        config_file.write_text("invalid: yaml: content:")

        with pytest.raises(ConfigurationError):
            load_yaml_file(config_file)

    def test_save_yaml_file(self, temp_dir):
        """Test saving a YAML file."""
        config_file = temp_dir / "output.yaml"
        config = {"test": "value", "nested": {"key": 123}}

        save_yaml_file(config_file, config)

        assert config_file.exists()
        loaded = yaml.safe_load(config_file.read_text())
        assert loaded == config

    def test_load_config_defaults(self, temp_dir, monkeypatch):
        """Test loading config with defaults when no config files exist."""
        monkeypatch.setenv("INKARMS_HOME", str(temp_dir / ".inkarms"))

        config = load_config(skip_project=True)

        assert config.providers.default == "anthropic/claude-sonnet-4-20250514"
        assert config.security.sandbox.enable is True

    def test_load_config_with_global(self, temp_dir, monkeypatch):
        """Test loading config merges global config."""
        inkarms_home = temp_dir / ".inkarms"
        inkarms_home.mkdir()
        monkeypatch.setenv("INKARMS_HOME", str(inkarms_home))

        # Create global config
        global_config = inkarms_home / "config.yaml"
        global_config.write_text("providers:\n  default: 'custom-model'\n")

        config = load_config(skip_project=True)

        assert config.providers.default == "custom-model"

    def test_load_config_with_profile(self, temp_dir, monkeypatch):
        """Test loading config with profile override."""
        inkarms_home = temp_dir / ".inkarms"
        inkarms_home.mkdir()
        profiles_dir = inkarms_home / "profiles"
        profiles_dir.mkdir()
        monkeypatch.setenv("INKARMS_HOME", str(inkarms_home))

        # Create global config
        global_config = inkarms_home / "config.yaml"
        global_config.write_text("providers:\n  default: 'global-model'\n")

        # Create profile config
        profile_config = profiles_dir / "work.yaml"
        profile_config.write_text("providers:\n  default: 'work-model'\n")

        config = load_config(profile="work", skip_project=True)

        assert config.providers.default == "work-model"

    def test_load_config_env_override(self, temp_dir, monkeypatch):
        """Test environment variable overrides."""
        monkeypatch.setenv("INKARMS_HOME", str(temp_dir / ".inkarms"))
        monkeypatch.setenv("INKARMS_PROVIDERS_DEFAULT", "env-model")

        config = load_config(skip_project=True)

        assert config.providers.default == "env-model"

    def test_load_config_env_boolean(self, temp_dir, monkeypatch):
        """Test environment variable boolean parsing."""
        monkeypatch.setenv("INKARMS_HOME", str(temp_dir / ".inkarms"))
        monkeypatch.setenv("INKARMS_SECURITY_SANDBOX_ENABLE", "false")

        config = load_config(skip_project=True)

        assert config.security.sandbox.enable is False


# =============================================================================
# Setup Tests
# =============================================================================


class TestSetup:
    """Tests for the setup module."""

    def test_create_directory_structure(self, temp_dir, monkeypatch):
        """Test directory structure creation."""
        monkeypatch.setenv("INKARMS_HOME", str(temp_dir / ".inkarms"))

        directories = create_directory_structure()

        assert (temp_dir / ".inkarms").exists()
        assert (temp_dir / ".inkarms" / "profiles").exists()
        assert (temp_dir / ".inkarms" / "skills").exists()
        assert (temp_dir / ".inkarms" / "memory").exists()
        assert (temp_dir / ".inkarms" / "secrets").exists()
        assert (temp_dir / ".inkarms" / "cache").exists()

        # Check secrets directory permissions
        secrets_dir = temp_dir / ".inkarms" / "secrets"
        # 0o700 = owner read/write/execute only
        assert secrets_dir.stat().st_mode & 0o777 == 0o700

    def test_create_default_config(self, temp_dir, monkeypatch):
        """Test default config file creation."""
        monkeypatch.setenv("INKARMS_HOME", str(temp_dir / ".inkarms"))

        config_path = create_default_config()

        assert config_path is not None
        assert config_path.exists()

        # Verify it's valid YAML with expected content
        content = yaml.safe_load(config_path.read_text())
        assert "providers" in content
        assert "security" in content

    def test_create_default_config_no_overwrite(self, temp_dir, monkeypatch):
        """Test that existing config is not overwritten by default."""
        inkarms_home = temp_dir / ".inkarms"
        inkarms_home.mkdir()
        monkeypatch.setenv("INKARMS_HOME", str(inkarms_home))

        config_path = inkarms_home / "config.yaml"
        config_path.write_text("existing: config")

        result = create_default_config(overwrite=False)

        assert result is None
        assert config_path.read_text() == "existing: config"

    def test_is_initialized(self, temp_dir, monkeypatch):
        """Test initialization check."""
        inkarms_home = temp_dir / ".inkarms"
        monkeypatch.setenv("INKARMS_HOME", str(inkarms_home))

        assert is_initialized() is False

        inkarms_home.mkdir()
        (inkarms_home / "config.yaml").write_text("test: true")

        assert is_initialized() is True

    def test_run_setup(self, temp_dir, monkeypatch):
        """Test full setup process."""
        monkeypatch.setenv("INKARMS_HOME", str(temp_dir / ".inkarms"))

        results = run_setup()

        assert results["config_created"] is True
        assert results["already_initialized"] is False
        assert "home" in results["directories"]
        assert (temp_dir / ".inkarms" / "config.yaml").exists()

    def test_run_setup_already_initialized(self, temp_dir, monkeypatch):
        """Test setup when already initialized."""
        inkarms_home = temp_dir / ".inkarms"
        inkarms_home.mkdir()
        (inkarms_home / "config.yaml").write_text("existing: config")
        monkeypatch.setenv("INKARMS_HOME", str(inkarms_home))

        results = run_setup()

        assert results["already_initialized"] is True
        assert results["config_created"] is False

    def test_create_project_config(self, temp_dir):
        """Test project config creation."""
        config_path = create_project_config(path=temp_dir)

        assert config_path is not None
        assert config_path.exists()
        assert (temp_dir / ".inkarms" / "project.yaml").exists()
        assert (temp_dir / ".inkarms" / "skills").exists()

        # Verify content
        content = yaml.safe_load(config_path.read_text())
        assert "_meta" in content

    def test_create_profile(self, temp_dir, monkeypatch):
        """Test profile creation."""
        monkeypatch.setenv("INKARMS_HOME", str(temp_dir / ".inkarms"))
        profiles_dir = temp_dir / ".inkarms" / "profiles"
        profiles_dir.mkdir(parents=True)

        profile_path = create_profile("work", description="Work profile")

        assert profile_path is not None
        assert profile_path.exists()

        content = yaml.safe_load(profile_path.read_text())
        assert content["_meta"]["name"] == "work"
        assert content["_meta"]["description"] == "Work profile"


# =============================================================================
# Path Tests
# =============================================================================


class TestPaths:
    """Tests for path utilities."""

    def test_get_inkarms_home_default(self, monkeypatch):
        """Test default home path."""
        monkeypatch.delenv("INKARMS_HOME", raising=False)
        home = get_inkarms_home()
        assert home == Path.home() / ".inkarms"

    def test_get_inkarms_home_env(self, monkeypatch):
        """Test custom home path via environment."""
        monkeypatch.setenv("INKARMS_HOME", "/custom/path")
        home = get_inkarms_home()
        assert home == Path("/custom/path")

    def test_get_global_config_path(self, monkeypatch):
        """Test global config path."""
        monkeypatch.setenv("INKARMS_HOME", "/test/inkarms")
        path = get_global_config_path()
        assert path == Path("/test/inkarms/config.yaml")

    def test_get_profile_path(self, monkeypatch):
        """Test profile path."""
        monkeypatch.setenv("INKARMS_HOME", "/test/inkarms")
        path = get_profile_path("work")
        assert path == Path("/test/inkarms/profiles/work.yaml")
