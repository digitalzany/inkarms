"""
Core logic for the configuration wizard.

This module defines the wizard state, steps, and logic for updating the configuration.
It is UI-agnostic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from inkarms.config.loader import clear_config_cache, load_config, load_yaml_file
from inkarms.config.merger import deep_merge
from inkarms.config.setup import create_default_config, create_directory_structure
from inkarms.secrets import SecretsManager
from inkarms.storage.paths import get_global_config_path

# Path to wizard configuration definition
WIZARD_CONFIG_PATH = Path(__file__).parent.parent / "defaults" / "config_wizard.yaml"


def load_wizard_definition() -> dict[str, Any]:
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
    api_key: str | None = None
    sandbox_mode: str = "blacklist"
    enable_tools: bool = True
    config_path: Path | None = None

    # Agent settings
    approval_mode: Literal["auto", "manual", "disabled"] = "manual"
    max_iterations: int = 10

    # Context / memory settings
    compaction_strategy: Literal["summarize", "truncate", "sliding_window"] = "summarize"
    auto_compact_threshold: float = 0.7

    # Cost settings
    daily_budget: float | None = None
    block_on_exceed: bool = False

    # Hub settings
    hub_enabled: bool = False
    hub_port: int = 18750
    hub_trust_localhost: bool = True

    # Platform settings — keyed by platform name (telegram/slack/discord)
    # Each value: {"enabled": bool, "bot_token": str, ...}
    platforms: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Tool secrets
    brave_api_key: str | None = None

    # Provider model discovery
    auto_discover_models: bool = False

    # Advanced options (arbitrary extra config for future steps)
    advanced_options: dict[str, Any] = Field(default_factory=dict)

    def apply(self, data: dict[str, Any]) -> None:
        """Apply a step result data dict to the state.

        Known keys are dispatched to typed fields. Unknown keys are stored in
        advanced_options for forward compatibility.
        """
        known = {
            "mode", "provider", "model", "api_key",
            "sandbox_mode", "enable_tools",
            "approval_mode", "max_iterations",
            "compaction_strategy", "auto_compact_threshold",
            "daily_budget", "block_on_exceed",
            "hub_enabled", "hub_port", "hub_trust_localhost",
            "platforms", "brave_api_key",
            "auto_discover_models",
        }
        for key, value in data.items():
            if key in known:
                object.__setattr__(self, key, value)
            else:
                self.advanced_options[key] = value

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

            # Agent
            self.enable_tools = config.agent.enable_tools
            self.approval_mode = config.agent.approval_mode
            self.max_iterations = config.agent.max_iterations

            # Context
            self.auto_compact_threshold = config.context.auto_compact_threshold
            self.compaction_strategy = config.context.compaction.strategy

            # Cost
            self.daily_budget = config.cost.budgets.daily
            self.block_on_exceed = config.cost.alerts.block_on_exceed

            # Hub
            self.hub_enabled = config.hub.enable
            self.hub_port = config.hub.port
            self.hub_trust_localhost = config.hub.trust_localhost

            # Platforms and tool secrets
            secrets_mgr = SecretsManager()
            self.platforms = _load_platform_state(config, secrets_mgr)
            try:
                brave_key = secrets_mgr.get("brave_search")
            except Exception:
                brave_key = None
            self.brave_api_key = (
                brave_key
                or os.environ.get("BRAVE_API_KEY")
                or os.environ.get("BRAVE_SEARCH_API_KEY")
                or None
            )

            # Provider model discovery
            self.auto_discover_models = config.providers.auto_discover_models

            # Try to load API key for the current provider
            try:
                secrets = SecretsManager()
                if self.provider and secrets.exists(self.provider):
                    self.api_key = secrets.get(self.provider)
            except Exception:
                pass

        except Exception:
            # Ignore errors if config doesn't exist or is invalid
            pass


def _load_platform_state(config: Any, secrets_mgr: SecretsManager) -> dict[str, Any]:
    """Load platform state: secrets from SecretsManager, non-secrets from config."""
    from inkarms.platforms.adapters import get_platform_metadata  # noqa: PLC0415

    result: dict[str, Any] = {}
    for platform_key, _, wizard_fields in get_platform_metadata():
        platform_cfg = getattr(config.platforms, platform_key, None)
        if not (platform_cfg and platform_cfg.enable):
            continue
        entry: dict[str, Any] = {"enabled": True}
        for wf in wizard_fields:
            if wf.is_secret:
                val = secrets_mgr.get(f"{platform_key}_{wf.key}")
            else:
                val = getattr(platform_cfg, wf.key, None)
            if val:
                entry[wf.key] = val
        result[platform_key] = entry
    return result


def save_wizard_config(state: WizardState) -> Path:
    """Save the wizard configuration to the global config file.

    Only updates fields that the wizard manages, preserving all other
    user configuration.
    """
    create_directory_structure()

    config_path = get_global_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        create_default_config()

    existing_config: dict[str, Any] = load_yaml_file(config_path)
    wizard_updates = _build_wizard_updates(state)

    # Save provider API key securely
    if state.api_key:
        try:
            SecretsManager().set(state.provider, state.api_key)
        except Exception as e:
            raise RuntimeError(f"Failed to save API key: {e}") from e

    merged_config = deep_merge(existing_config, wizard_updates)

    yaml_content = yaml.dump(
        merged_config, default_flow_style=False, sort_keys=False, allow_unicode=True
    )
    final_content = f"# InkArms Configuration\n# Updated by Config Wizard\n\n{yaml_content}"
    config_path.write_text(final_content, encoding="utf-8")
    clear_config_cache()

    return config_path


def _build_wizard_updates(state: WizardState) -> dict[str, Any]:
    """Build the dict of config fields the wizard manages."""
    updates: dict[str, Any] = {
        "providers": {
            "default": state.model,
            "auto_discover_models": state.auto_discover_models,
        },
        "security": {
            "sandbox": {
                "enable": state.sandbox_mode != "disabled",
                "mode": state.sandbox_mode,
            },
        },
        "agent": {"enable_tools": state.enable_tools},
    }

    if state.brave_api_key:
        try:
            SecretsManager().set("brave_search", state.brave_api_key)
        except Exception as e:
            raise RuntimeError(f"Failed to save Brave API key: {e}") from e

    if state.mode == "advanced":
        updates["agent"].update({
            "approval_mode": state.approval_mode,
            "max_iterations": state.max_iterations,
        })
        updates["context"] = {
            "auto_compact_threshold": state.auto_compact_threshold,
            "compaction": {"strategy": state.compaction_strategy},
        }
        cost: dict[str, Any] = {"alerts": {"block_on_exceed": state.block_on_exceed}}
        if state.daily_budget is not None:
            cost["budgets"] = {"daily": state.daily_budget}
        updates["cost"] = cost
        updates["hub"] = {
            "enable": state.hub_enabled,
            "port": state.hub_port,
            "trust_localhost": state.hub_trust_localhost,
        }
        platform_updates = _build_platform_updates(state)
        if platform_updates:
            any_enabled = any(v.get("enable") for v in platform_updates.values())
            updates["platforms"] = {"enable": any_enabled, **platform_updates}
        if state.advanced_options:
            updates = deep_merge(updates, state.advanced_options)

    return updates


def _build_platform_updates(state: WizardState) -> dict[str, Any]:
    """Store secret tokens in SecretsManager; write enable flag and non-secret fields to config."""
    from inkarms.platforms.adapters import get_platform_metadata  # noqa: PLC0415

    secrets = SecretsManager()
    result: dict[str, Any] = {}

    for platform_key, _, wizard_fields in get_platform_metadata():
        platform = state.platforms.get(platform_key, {})
        if not platform.get("enabled"):
            continue
        entry: dict[str, Any] = {"enable": True}
        for wf in wizard_fields:
            value = platform.get(wf.key)
            if not value:
                continue
            if wf.is_secret:
                secrets.set(f"{platform_key}_{wf.key}", value)
            else:
                entry[wf.key] = value
        result[platform_key] = entry

    return result


