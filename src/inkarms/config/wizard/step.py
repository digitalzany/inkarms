"""
Base types for the configuration wizard step registry.

Each wizard step is a class that inherits from WizardStep and implements run().
The WizardEngine drives navigation using the StepResult returned by each step.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState
    from inkarms.ui.backends.rich_backend.backend import RichBackend


class StepAction(Enum):
    """Action returned by a wizard step."""

    NEXT = "next"
    BACK = "back"
    CANCEL = "cancel"


@dataclass
class StepResult:
    """Result returned by a wizard step after the user completes it."""

    action: StepAction
    data: dict[str, Any] = field(default_factory=dict)


#: Sentinel value returned by _selection_with_back when the user picks ← Back.
BACK_SENTINEL = "__back__"


class WizardStep(ABC):
    """Abstract base class for all wizard steps.

    Subclasses must set ``step_key`` (a unique string identifier) and optionally
    restrict ``modes`` to control which wizard modes include this step.
    """

    step_key: str = ""
    #: Tuple of mode strings this step is applicable for ("quick" / "advanced").
    modes: tuple[str, ...] = ("quick", "advanced")

    def __init__(self, backend: RichBackend) -> None:
        self.backend = backend

    def is_applicable(self, state: WizardState) -> bool:
        """Return True if this step should run given the current wizard state."""
        return state.mode in self.modes

    @abstractmethod
    def run(self, state: WizardState, progress: str) -> StepResult:
        """Run the step interaction and return a StepResult.

        Args:
            state: Current wizard state (read-only during the step; engine applies data).
            progress: Human-readable progress string, e.g. "Step 2 of 5".

        Returns:
            StepResult with action NEXT (include data dict), BACK, or CANCEL.
        """
        ...

    def _selection_with_back(
        self,
        title: str,
        options: list[tuple[str, str, str]],
        message: str,
    ) -> str | None:
        """Show a selection menu with a ← Back option prepended.

        Args:
            title: Menu title.
            options: List of (value, label, description) tuples.
            message: Subtitle/prompt text shown under the title.

        Returns:
            BACK_SENTINEL if ← Back was chosen, None if the user cancelled
            (e.g. Ctrl-C), or the selected option value string.
        """
        opts: list[tuple[str, str, str]] = [
            (BACK_SENTINEL, "← Back", "Return to previous step"),
            *options,
        ]
        return self.backend.get_selection(title, opts, message)
