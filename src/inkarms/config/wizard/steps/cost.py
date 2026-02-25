"""Cost step — daily budget and block_on_exceed (advanced only)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from inkarms.config.wizard.step import BACK_SENTINEL, StepAction, StepResult, WizardStep

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState


class CostStep(WizardStep):
    """Configure daily budget and what to do when it is exceeded."""

    step_key = "cost"
    modes = ("advanced",)

    def run(self, state: WizardState, progress: str) -> StepResult:
        # --- Daily budget ---
        default_budget = str(state.daily_budget) if state.daily_budget is not None else ""
        while True:
            raw = self.backend.get_text_input(
                f"Daily Cost Budget  [{progress}]",
                "Budget in USD (leave blank for no limit): ",
                default=default_budget,
            )
            if raw is None:
                return StepResult(action=StepAction.BACK)

            raw = raw.strip()
            if not raw:
                daily_budget = None
                break
            try:
                daily_budget = float(raw)
                if daily_budget > 0:
                    break
                self.backend.display_error("Budget must be a positive number.")
            except ValueError:
                self.backend.display_error("Please enter a number (e.g. 5.00) or leave blank.")

        if daily_budget is None:
            return StepResult(
                action=StepAction.NEXT,
                data={"daily_budget": None, "block_on_exceed": False},
            )

        # --- Block on exceed (only relevant if budget is set) ---
        action_choice = self._selection_with_back(
            f"Budget Enforcement  [{progress}]",
            [
                ("warn", "Warn only", "Show a warning but continue processing"),
                ("block", "Block requests", "Hard-stop new requests when budget is exceeded"),
            ],
            f"What happens when the ${daily_budget:.2f}/day limit is reached?",
        )
        if action_choice is None:
            return StepResult(action=StepAction.CANCEL)
        if action_choice == BACK_SENTINEL:
            # Let user re-enter budget
            return StepResult(action=StepAction.BACK)

        return StepResult(
            action=StepAction.NEXT,
            data={
                "daily_budget": daily_budget,
                "block_on_exceed": action_choice == "block",
            },
        )
