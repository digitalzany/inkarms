"""Context step — compaction strategy and auto-compact threshold (advanced only)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from inkarms.config.wizard.step import BACK_SENTINEL, StepAction, StepResult, WizardStep

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState


class ContextStep(WizardStep):
    """Configure context compaction strategy and threshold."""

    step_key = "context"
    modes = ("advanced",)

    def run(self, state: WizardState, progress: str) -> StepResult:
        # --- Compaction strategy ---
        strategy = self._selection_with_back(
            f"Context Compaction  [{progress}]",
            [
                ("summarize", "Summarize (Recommended)", "AI generates a summary of older turns"),
                ("truncate", "Truncate", "Remove oldest messages when context fills up"),
                ("sliding_window", "Sliding Window", "Keep only the most recent N turns"),
            ],
            "How should InkArms handle context when it gets too long?",
        )
        if strategy is None:
            return StepResult(action=StepAction.CANCEL)
        if strategy == BACK_SENTINEL:
            return StepResult(action=StepAction.BACK)

        # --- Auto-compact threshold ---
        while True:
            raw = self.backend.get_text_input(
                f"Auto-Compact Threshold  [{progress}]",
                "Compact when context is this full (0.50-0.95): ",
                default=str(state.auto_compact_threshold),
            )
            if raw is None:
                return StepResult(action=StepAction.BACK)

            raw = raw.strip()
            try:
                threshold = float(raw)
                if 0.5 <= threshold <= 0.95:
                    break
                self.backend.display_error("Please enter a value between 0.50 and 0.95.")
            except ValueError:
                self.backend.display_error("Please enter a decimal number (e.g. 0.70).")

        return StepResult(
            action=StepAction.NEXT,
            data={
                "compaction_strategy": strategy,
                "auto_compact_threshold": threshold,
            },
        )
