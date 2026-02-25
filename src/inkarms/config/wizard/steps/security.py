"""Security step — sandbox mode selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from inkarms.config.wizard.step import BACK_SENTINEL, StepAction, StepResult, WizardStep

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState


class SecurityStep(WizardStep):
    """Configure the sandbox execution mode."""

    step_key = "security"
    modes = ("quick",)

    def run(self, _state: WizardState, progress: str) -> StepResult:
        options = [
            ("blacklist", "Blacklist (Default)", "Block known dangerous commands"),
            ("whitelist", "Whitelist", "Only allow explicitly permitted commands"),
            ("prompt", "Prompt Mode", "Ask before every command execution"),
            ("disabled", "Disabled", "No restrictions — unsafe, use with caution"),
        ]

        sandbox = self._selection_with_back(
            f"Security Sandbox  [{progress}]",
            options,
            "How should InkArms handle command execution?",
        )

        if sandbox is None:
            return StepResult(action=StepAction.CANCEL)
        if sandbox == BACK_SENTINEL:
            return StepResult(action=StepAction.BACK)

        return StepResult(action=StepAction.NEXT, data={"sandbox_mode": sandbox})
