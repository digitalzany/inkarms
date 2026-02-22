"""
Core logic for the configuration wizard.

This module defines the wizard state, steps, and logic for updating the configuration.
It is UI-agnostic.
"""

import yaml
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from inkarms.config.loader import load_config, load_yaml_file
from inkarms.config.merger import deep_merge
from inkarms.config.setup import create_directory_structure, create_default_config
from inkarms.secrets import SecretsManager
from inkarms.storage.paths import get_global_config_path

# Path to wizard configuration definition
WIZARD_CONFIG_PATH = Path(__file__).parent.parent / "defaults" / "config_wizard.yaml"


def load_wizard_definition() -> Dict[str, Any]:
    """Load the wizard UI definition from YAML."""
    if WIZARD_CONFIG_PATH.exists():
        try:
            return yaml.safe_load(WIZARD_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


class WizardState(BaseModel):
    """Holds the state of the wizard during execution."""

    mode: str = "quick"  # quick | advanced | skip
    provider: str = "anthropic"
    model: str = "anthropic/claude-sonnet-4.5"
    api_key: Optional[str] = None
    sandbox_mode: str = "blacklist"
    enable_tools: bool = True
    config_path: Optional[Path] = None

    # Advanced options (stored as dict for flexibility)
    advanced_options: Dict[str, Any] = Field(default_factory=dict)

    def load_existing_config(self) -> None:
        """Load state from existing configuration if available."""
        try:
            config = load_config()

            # Provider & Model
            if config.providers.default:
                self.model = config.providers.default
                if "/" in self.model:
                    self.provider = self.model.split("/")[0]

            # Security
            if config.security.sandbox.mode:
                self.sandbox_mode = config.security.sandbox.mode

            # Tools
            self.enable_tools = config.agent.enable_tools

            # Try to load API key for the current provider
            try:
                secrets = SecretsManager()
                if self.provider and secrets.exists(self.provider):
                    # We don't necessarily need the actual key value if we just want to know it exists
                    # But if we want to pre-fill (masked), we might need it.
                    # For security, maybe we just flag that it's set?
                    # But the WizardState expects string.
                    self.api_key = secrets.get(self.provider)
            except Exception:
                pass

        except Exception:
            # Ignore errors if config doesn't exist or is invalid
            pass


def save_wizard_config(state: WizardState) -> Path:
    """Save the wizard configuration to the global config file.

    Only updates fields that the wizard manages, preserving all other
    user configuration.
    """
    create_directory_structure()

    config_path = get_global_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing user config to preserve non-wizard fields
    if not config_path.exists():
        create_default_config()

    existing_config: dict[str, Any] = load_yaml_file(config_path)

    # Build only the fields the wizard actually changes
    wizard_updates: dict[str, Any] = {
        "providers": {
            "default": state.model,
        },
        "security": {
            "sandbox": {
                "enable": state.sandbox_mode != "disabled",
                "mode": state.sandbox_mode,
            },
        },
    }

    # Merge advanced options if present
    if state.mode == "advanced" and state.advanced_options:
        wizard_updates = deep_merge(wizard_updates, state.advanced_options)

    # Save API Key securely
    if state.api_key:
        try:
            secrets = SecretsManager()
            secrets.set(state.provider, state.api_key)
        except Exception as e:
            raise RuntimeError(f"Failed to save API key: {e}")

    # Deep merge wizard updates into existing config
    merged_config = deep_merge(existing_config, wizard_updates)

    # Write YAML
    yaml_content = yaml.dump(
        merged_config, default_flow_style=False, sort_keys=False, allow_unicode=True
    )

    # Add header
    final_content = f"# InkArms Configuration\n# Updated by Config Wizard\n\n{yaml_content}"
    config_path.write_text(final_content, encoding="utf-8")

    return config_path
