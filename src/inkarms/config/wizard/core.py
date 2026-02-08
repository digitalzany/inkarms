"""
Core logic for the configuration wizard.

This module defines the wizard state, steps, and logic for updating the configuration.
It is UI-agnostic.
"""

import yaml
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from inkarms.config.loader import load_config
from inkarms.config.setup import create_directory_structure
from inkarms.secrets import SecretsManager
from inkarms.storage.paths import get_global_config_path

# Path to wizard configuration definition
WIZARD_CONFIG_PATH = Path(__file__).parent.parent / "defaults" / "config_wizard.yaml"


class WizardStep(Enum):
    WELCOME = auto()
    MODE_SELECTION = auto()
    PROVIDER_SELECTION = auto()
    MODEL_SELECTION = auto()
    API_KEY = auto()
    SECURITY_SANDBOX = auto()
    TOOLS_CONFIG = auto()
    CONFIRMATION = auto()
    COMPLETE = auto()


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
    sandbox_mode: str = "whitelist"
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
    """Save the wizard configuration to the global config file."""
    create_directory_structure()

    config_dict = {
        "providers": {
            "default": state.model,
            "fallback": [],
            "aliases": {},
        },
        "security": {
            "sandbox": {
                "enable": state.sandbox_mode != "disabled",
                "mode": state.sandbox_mode,
            },
            # Basic whitelist from legacy wizard
            "whitelist": [
                "ls",
                "cat",
                "head",
                "tail",
                "grep",
                "find",
                "echo",
                "git",
                "python",
                "pip",
                "npm",
                "node",
                "mkdir",
                "cp",
                "mv",
            ],
            "blacklist": [
                "rm -rf",
                "sudo",
                "chmod",
                "chown",
                "dd",
                "curl | bash",
                "wget | bash",
            ],
        },
        "skills": {
            "smart_index": {
                "enable": True,
                "mode": "keyword",
            },
        },
        "ui": {
            "backend": "auto",  # Default
            "theme": "default",
        },
    }

    # Merge advanced options if present
    if state.mode == "advanced":
        # logic to merge advanced options
        if state.advanced_options:
            # simple merge for now
            pass

    # 3. Save API Key securely
    if state.api_key:
        try:
            secrets = SecretsManager()
            secrets.set(state.provider, state.api_key)
        except Exception as e:
            # We can't log here easily without importing logger, rely on return/exception
            raise RuntimeError(f"Failed to save API key: {e}")

    # 4. Write YAML
    import yaml

    config_path = get_global_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    yaml_content = yaml.dump(
        config_dict, default_flow_style=False, sort_keys=False, allow_unicode=True
    )

    # Add header
    final_content = f"# InkArms Configuration\n# Generated by Config Wizard\n\n{yaml_content}"
    config_path.write_text(final_content, encoding="utf-8")

    return config_path
