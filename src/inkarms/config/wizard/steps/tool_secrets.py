"""Tool secrets step — configure API keys required by optional tools (e.g. Brave Search)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from inkarms.config.wizard.step import BACK_SENTINEL, StepAction, StepResult, WizardStep

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState

_BACK = object()   # sentinel for "user backed out"
_CANCEL = object() # sentinel for "user cancelled"


class ToolSecretsStep(WizardStep):
    """Configure API keys for optional tools like Brave Web Search."""

    step_key = "tool_secrets"
    modes = ("quick",)

    def run(self, state: WizardState, progress: str) -> StepResult:
        env_key = os.environ.get("BRAVE_API_KEY") or os.environ.get("BRAVE_SEARCH_API_KEY")
        existing_key = state.brave_api_key or env_key

        key, signal = self._decide_brave_key(existing_key, progress)

        if signal is _CANCEL:
            return StepResult(action=StepAction.CANCEL)
        if signal is _BACK:
            return StepResult(action=StepAction.BACK)

        return StepResult(action=StepAction.NEXT, data={"brave_api_key": key})

    def _decide_brave_key(
        self, existing_key: str | None, progress: str
    ) -> tuple[str | None, object]:
        """Return (api_key | None, signal) where signal is None / _BACK / _CANCEL."""
        if existing_key:
            return self._handle_existing_key(existing_key, progress)
        return self._handle_new_key(progress)

    def _handle_existing_key(
        self, existing_key: str, progress: str
    ) -> tuple[str | None, object]:
        choice = self._selection_with_back(
            f"Web Search Tool  [{progress}]",
            [
                ("keep", "Keep existing Brave API key", "Web Search is already configured"),
                ("update", "Update Brave API key", "Enter a new Brave Search API key"),
                ("disable", "Disable Web Search", "Remove the configured key"),
            ],
            "A Brave Search API key is already configured.",
        )
        if choice is None:
            return None, _CANCEL
        if choice == BACK_SENTINEL:
            return None, _BACK
        if choice == "keep":
            return existing_key, None
        if choice == "disable":
            return None, None
        # "update"
        return self._prompt_for_key(progress)

    def _handle_new_key(self, progress: str) -> tuple[str | None, object]:
        enable = self._selection_with_back(
            f"Web Search Tool  [{progress}]",
            [
                ("yes", "Enable Web Search (Brave API)", "Requires a free Brave Search API key"),
                ("no", "Skip", "Web Search will not be available"),
            ],
            "InkArms can search the web using Brave Search. Enable it?",
        )
        if enable is None:
            return None, _CANCEL
        if enable == BACK_SENTINEL:
            return None, _BACK
        if enable == "no":
            return None, None
        return self._prompt_for_key(progress)

    def _prompt_for_key(self, progress: str) -> tuple[str | None, object]:
        api_key = self.backend.get_text_input(
            f"Brave Search API Key  [{progress}]",
            "Enter API key (hidden): ",
            password=True,
        )
        if api_key is None:
            return None, _BACK
        return api_key.strip() or None, None
