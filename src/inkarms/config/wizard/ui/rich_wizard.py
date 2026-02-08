"""
Rich/Textual UI implementation for the configuration wizard.

This module implements the wizard UI using the native RichBackend primitives
(get_selection, get_text_input, etc.) to ensure seamless integration.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Tuple
from inkarms.config.wizard.core import (
    WizardState,
    save_wizard_config,
    load_wizard_definition,
)
from inkarms.config.providers import get_provider_choices, get_model_choices
from inkarms.secrets.manager import DecryptionError

if TYPE_CHECKING:
    from inkarms.ui.rich_backend import RichBackend


class RichWizard:
    """Native Rich/Textual UI configuration wizard."""

    def __init__(self, backend: "RichBackend"):
        self.backend = backend
        self.state = WizardState()
        self.config_def = load_wizard_definition()

        # Load existing config if available
        self.state.load_existing_config()

    def _get_step_def(self, step_key: str) -> Dict[str, Any]:
        """Get step definition from loaded config or defaults."""
        return self.config_def.get("steps", {}).get(step_key, {})

    def _get_options(self, step_key: str) -> List[Tuple[str, str, str]]:
        """Get formatted options tuple list for a step."""
        step = self._get_step_def(step_key)
        options = step.get("options", [])
        return [(opt["value"], opt["label"], opt.get("description", "")) for opt in options]

    def run(self) -> bool:
        """Run the wizard flow. Returns True if config was created or skipped."""

        # 1. Welcome / Mode Selection
        welcome_def = self._get_step_def("welcome")
        options = self._get_options("welcome")
        if not options:
            # Fallback if config failed to load
            options = [
                ("quick", "Quick Start", "Recommended: Sensible defaults"),
                ("advanced", "Advanced Setup", "Customize all options"),
                ("skip", "Skip Setup", "Configure manually later"),
            ]

        mode = self.backend.get_selection(
            welcome_def.get("title", "InkArms Setup"),
            options,
            welcome_def.get("message", "Welcome! How would you like to configure InkArms?"),
        )

        if not mode:
            return False

        self.state.mode = mode

        # Handle Skip
        if self.state.mode == "skip":
            # We treat 'skip' as success but don't save config.
            self.backend.display_info(
                "Setup skipped. You can configure manually in ~/.inkarms/config.yaml"
            )
            return True  # Return True to proceed to main app

        # 2. Provider Selection
        provider_def = self._get_step_def("provider")
        provider = self.backend.get_selection(
            provider_def.get("title", "Select AI Provider"),
            get_provider_choices(),
            provider_def.get("message", "Choose your primary AI provider"),
        )

        if not provider:
            return False

        self.state.provider = provider

        # 3. Model Selection
        model_def = self._get_step_def("model")
        model_choices = get_model_choices(provider)
        if not model_choices:
            # Fallback if no models defined for provider
            model_choices = [(f"{provider}/default", "Default Model", "")]

        model = self.backend.get_selection(
            model_def.get("title", f"Select Model for {provider.title()}"),
            model_choices,
            model_def.get("message", "Choose the default model to use"),
        )

        if not model:
            return False

        # Ensure model has provider prefix
        if "/" not in model:
            self.state.model = f"{provider}/{model}"
        else:
            self.state.model = model

        # 4. API Key (skip for ollama)
        if provider != "ollama":
            from inkarms.secrets import SecretsManager

            secrets_manager = SecretsManager()
            api_def = self._get_step_def("api_key")
            title = api_def.get("title", "{provider} API Key").format(provider=provider.title())
            base_message = api_def.get("message", "Enter API Key (hidden): ")

            # Check if we already have a key for this provider
            existing_key_set = False

            if secrets_manager.exists(provider):
                try:
                    self.state.api_key = secrets_manager.get(provider)
                    existing_key_set = True

                except DecryptionError:
                    self.backend.display_error(
                        "Could not retrieve existing key. Please enter it again."
                    )

            update_key = True
            if existing_key_set:
                # Ask user if they want to update the key
                choice = self.backend.get_selection(
                    f"{provider.title()} API Key",
                    [
                        ("keep", "Keep existing API Key", "Use currently configured key"),
                        ("update", "Update API Key", "Enter a new API key"),
                    ],
                    "An API key is already configured for this provider.",
                )
                if not choice:
                    return False

                if choice == "keep":
                    update_key = False

            if update_key:
                api_key = self.backend.get_text_input(title, base_message, password=True)

                if api_key is None:
                    return False

                self.state.api_key = api_key.strip()
                secrets_manager.set(provider, self.state.api_key)

            # If keep, self.state.api_key is already set above

        # 5. Advanced Settings (if mode == "advanced")
        if self.state.mode == "advanced":
            # Security Sandbox
            sec_def = self._get_step_def("security")
            sec_opts = self._get_options("security")
            if not sec_opts:
                sec_opts = [
                    ("whitelist", "Whitelist (Recommended)", "Only allow safe commands"),
                    ("prompt", "Prompt Mode", "Ask before every command"),
                    ("disabled", "Disabled", "Allow all commands (Unsafe)"),
                ]

            sandbox = self.backend.get_selection(
                sec_def.get("title", "Security Sandbox"),
                sec_opts,
                sec_def.get("message", "How should InkArms handle command execution?"),
            )
            if not sandbox:
                return False
            self.state.sandbox_mode = sandbox

            # Tools
            tools_def = self._get_step_def("tools")
            enable_tools = self.backend.confirm(
                tools_def.get("message", "Enable autonomous tool use (File I/O, Shell)?"),
                default=tools_def.get("default", True),
            )
            self.state.enable_tools = enable_tools

        # 6. Confirmation & Save
        try:
            config_path = save_wizard_config(self.state)
            self.backend.display_info(f"Configuration saved to {config_path}")

            # Update backend status immediately
            self.backend._status.provider = self.state.provider
            self.backend._status.model = self.state.model
            self.backend._status.api_key_set = bool(self.state.api_key)
            self.backend._configured = True

            return True

        except Exception as e:
            self.backend.display_error(f"Failed to save configuration: {e}")
            return False
