"""Agent step — tool approval mode and max iterations (advanced only)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from inkarms.config.wizard.step import BACK_SENTINEL, StepAction, StepResult, WizardStep

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState


class AgentStep(WizardStep):
    """Configure tool approval mode and iteration limit."""

    step_key = "agent"
    modes = ("advanced",)

    def run(self, state: WizardState, progress: str) -> StepResult:
        # --- Tool approval mode ---
        approval = self._selection_with_back(
            f"Tool Approval  [{progress}]",
            [
                ("manual", "Manual (Recommended)", "Dangerous tools prompt for approval"),
                ("auto", "Auto-approve", "All tools run without prompting"),
                ("disabled", "Disabled", "Tool use is turned off entirely"),
            ],
            "How should InkArms handle tool execution approval?",
        )
        if approval is None:
            return StepResult(action=StepAction.CANCEL)
        if approval == BACK_SENTINEL:
            return StepResult(action=StepAction.BACK)

        # --- Max iterations ---
        while True:
            raw = self.backend.get_text_input(
                f"Agent Iterations  [{progress}]",
                "Max agent loop iterations (1-50): ",
                default=str(state.max_iterations),
            )
            if raw is None:
                return StepResult(action=StepAction.BACK)

            raw = raw.strip()
            try:
                iterations = int(raw)
                if 1 <= iterations <= 50:
                    break
                self.backend.display_error("Please enter a number between 1 and 50.")
            except ValueError:
                self.backend.display_error("Please enter a valid integer.")

        return StepResult(
            action=StepAction.NEXT,
            data={"approval_mode": approval, "max_iterations": iterations},
        )
