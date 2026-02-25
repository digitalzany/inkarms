"""Provider step — provider selection → model selection → API key."""

from __future__ import annotations

from typing import TYPE_CHECKING

from inkarms.config.providers import get_model_choices, get_provider_choices
from inkarms.config.wizard.step import BACK_SENTINEL, StepAction, StepResult, WizardStep
from inkarms.secrets import DecryptionError, SecretsManager

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState


class ProviderStep(WizardStep):
    """Handles provider, model, and API key in a single step with internal back navigation."""

    step_key = "provider"
    modes = ("quick",)

    def run(self, state: WizardState, progress: str) -> StepResult:  # noqa: PLR0911
        provider_choices = get_provider_choices()

        # --- 1. Provider (re-shown when user backs from model) ---
        provider: str | None = None
        while provider is None:
            result = self._selection_with_back(
                f"Select AI Provider  [{progress}]",
                provider_choices,
                "Choose your primary AI provider",
            )
            if result is None:
                return StepResult(action=StepAction.CANCEL)
            if result == BACK_SENTINEL:
                return StepResult(action=StepAction.BACK)
            provider = result

        # --- 2. Model ---
        model = self._select_model(provider, provider_choices, progress)
        if model is StepAction.CANCEL:
            return StepResult(action=StepAction.CANCEL)
        if model is StepAction.BACK:
            return StepResult(action=StepAction.BACK)

        # Ensure model has provider prefix
        if "/" not in model:
            model = f"{provider}/{model}"

        # --- 3. API Key (skip for local providers like ollama) ---
        api_key, action = self._collect_api_key(provider, state.api_key, progress)
        if action == StepAction.CANCEL:
            return StepResult(action=StepAction.CANCEL)
        if action == StepAction.BACK:
            return StepResult(action=StepAction.BACK)

        # --- 4. Auto-discover models ---
        auto_discover = self._select_auto_discover(state.auto_discover_models, progress)
        if auto_discover is StepAction.CANCEL:
            return StepResult(action=StepAction.CANCEL)
        if auto_discover is StepAction.BACK:
            return StepResult(action=StepAction.BACK)

        return StepResult(
            action=StepAction.NEXT,
            data={
                "provider": provider,
                "model": model,
                "api_key": api_key,
                "auto_discover_models": auto_discover,
            },
        )

    def _select_model(
        self,
        initial_provider: str,
        provider_choices: list[tuple[str, str, str]],
        progress: str,
    ) -> str | StepAction:
        """Select a model, allowing the user to go back to provider selection."""
        provider = initial_provider
        while True:
            choices = get_model_choices(provider)
            if not choices:
                choices = [(f"{provider}/default", "Default Model", "")]

            model = self._selection_with_back(
                f"Select Model  [{progress}]",
                choices,
                f"Choose the default model for {provider.title()}",
            )
            if model is None:
                return StepAction.CANCEL
            if model != BACK_SENTINEL:
                return model

            # User backed from model — re-show provider selection
            p = self._selection_with_back(
                f"Select AI Provider  [{progress}]",
                provider_choices,
                "Choose your primary AI provider",
            )
            if p is None:
                return StepAction.CANCEL
            if p == BACK_SENTINEL:
                return StepAction.BACK
            provider = p

    def _select_auto_discover(
        self, current: bool, progress: str
    ) -> bool | StepAction:
        """Ask whether to auto-discover available models from the provider API."""
        current_label = "enabled" if current else "disabled"
        choice = self._selection_with_back(
            f"Model Discovery  [{progress}]",
            [
                ("disabled", "Disabled (recommended)", "Manually manage which models are listed"),
                ("enabled", "Enabled", "Fetch the live model list from the provider API on startup"),
            ],
            f"Auto-discover available models from provider API?  Currently: {current_label}",
        )
        if choice is None:
            return StepAction.CANCEL
        if choice == BACK_SENTINEL:
            return StepAction.BACK
        return choice == "enabled"

    def _collect_api_key(
        self,
        provider: str,
        current_api_key: str | None,
        progress: str,
    ) -> tuple[str | None, StepAction]:
        """Collect or confirm the provider API key. Returns (key, action)."""
        if provider == "ollama":
            return None, StepAction.NEXT

        secrets_manager = SecretsManager()
        existing_key_set = False

        if secrets_manager.exists(provider):
            try:
                current_api_key = secrets_manager.get(provider)
                existing_key_set = True
            except DecryptionError:
                self.backend.display_error("Could not decrypt existing key. Please enter it again.")

        if existing_key_set:
            choice = self._selection_with_back(
                f"{provider.title()} API Key  [{progress}]",
                [
                    ("keep", "Keep existing API key", "Use the currently configured key"),
                    ("update", "Update API key", "Enter a new API key"),
                ],
                "An API key is already configured for this provider.",
            )
            if choice is None:
                return None, StepAction.CANCEL
            if choice == BACK_SENTINEL:
                return None, StepAction.BACK
            if choice == "keep":
                return current_api_key, StepAction.NEXT

        api_key_input = self.backend.get_text_input(
            f"{provider.title()} API Key  [{progress}]",
            "Enter API key (hidden): ",
            password=True,
        )
        if api_key_input is None:
            return None, StepAction.BACK

        return api_key_input.strip() or current_api_key, StepAction.NEXT
