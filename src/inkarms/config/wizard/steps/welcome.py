"""Welcome step — mode selection (quick / advanced / skip)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from inkarms.config.wizard.step import StepAction, StepResult, WizardStep

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState


class WelcomeStep(WizardStep):
    """First step: lets the user choose Quick Start, Advanced Setup, or Skip."""

    step_key = "welcome"
    modes = ("quick", "advanced")  # Always shown — mode is set by this step

    def is_applicable(self, _state: WizardState) -> bool:
        # Always run regardless of mode (mode is unknown until this step completes)
        return True

    def run(self, _state: WizardState, progress: str) -> StepResult:
        options = [
            ("quick", "Quick Start", "Recommended: provider, API key, and security"),
            ("advanced", "Advanced Setup", "All options: hub, platforms, cost limits, and more"),
            ("skip", "Skip Setup", "Configure manually later (~/.inkarms/config.yaml)"),
        ]
        # No back on the first step — use plain get_selection
        mode = self.backend.get_selection(
            f"InkArms Setup  [{progress}]",
            options,
            "Welcome! How would you like to configure InkArms?",
        )

        if mode is None:
            return StepResult(action=StepAction.CANCEL)

        if mode == "skip":
            self.backend.display_info(
                "Setup skipped. You can configure manually at ~/.inkarms/config.yaml"
            )

        return StepResult(action=StepAction.NEXT, data={"mode": mode})
