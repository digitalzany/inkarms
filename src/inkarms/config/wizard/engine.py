"""
WizardEngine — drives the wizard flow with history-stack back navigation.

After WelcomeStep sets state.mode, the active step list is recomputed to include
only steps applicable to that mode. This lets new steps be added to the registry
without touching any navigation logic.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from inkarms.config.wizard.step import StepAction, WizardStep

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState

logger = logging.getLogger(__name__)


class WizardEngine:
    """Drives the wizard step flow.

    Navigation model:
    - Each step returns StepResult(NEXT | BACK | CANCEL).
    - On NEXT: state.apply(result.data) is called, cursor advances, current index
      is pushed to history.
    - On BACK: the last index is popped from history and becomes the new cursor.
      If there is no history (first step), cursor stays at 0.
    - On CANCEL: engine.run() returns False immediately.
    - After the WelcomeStep (step_key == "welcome"), _active is recomputed to
      include only steps where is_applicable(state) is True, and the cursor
      resets to 0.
    """

    def __init__(self, steps: list[WizardStep], state: WizardState) -> None:
        self._all_steps = steps
        self.state = state
        self._history: list[int] = []
        # Start with all steps; recomputed after welcome sets mode
        self._active: list[WizardStep] = list(steps)

    def run(self) -> bool:
        """Run the wizard to completion.

        Returns:
            True if the wizard completed (saved or skipped).
            False if the user cancelled.
        """
        cursor = 0
        while cursor < len(self._active):
            step = self._active[cursor]
            total = len(self._active)
            progress = f"Step {cursor + 1} of {total}"

            try:
                result = step.run(self.state, progress)
            except KeyboardInterrupt:
                return False
            except Exception as e:
                logger.error("Wizard step %r raised an error: %s", step.step_key, e)
                return False

            if result.action == StepAction.CANCEL:
                return False

            if result.action == StepAction.BACK:
                if self._history:
                    cursor = self._history.pop()
                else:
                    # Back at the first post-welcome step — restart from WelcomeStep
                    # so the user can switch between Quick/Advanced modes.
                    self._active = list(self._all_steps)
                    self._history = []
                    cursor = 0
                continue

            # NEXT: apply data and advance
            self.state.apply(result.data)

            if step.step_key == "welcome":
                # Recompute active step list now that mode is known.
                # Exclude the welcome step itself — it only ever runs once.
                self._active = [
                    s for s in self._all_steps
                    if s.step_key != "welcome" and s.is_applicable(self.state)
                ]
                self._history = []
                cursor = 0
                continue

            self._history.append(cursor)
            cursor += 1

        return True
