"""Tools step — two-level menu: tool picker → per-tool configuration.

Adding a new configurable tool:
  1. Create (or reuse) a WizardStep subclass for that tool's settings.
  2. Add an entry to ToolsStep._TOOLS and ToolsStep._build_options().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from inkarms.config.wizard.step import BACK_SENTINEL, StepAction, StepResult, WizardStep
from inkarms.config.wizard.steps.tool_secrets import ToolSecretsStep

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState


class ToolsStep(WizardStep):
    """Two-level tools configuration menu (advanced mode only).

    Top level: pick a tool to configure, or select Done.
    Tool level: delegates to that tool's own step.
    """

    step_key = "tools"
    modes = ("advanced",)

    def __init__(self, backend) -> None:
        super().__init__(backend)
        self._web_search = ToolSecretsStep(backend)

    def run(self, state: WizardState, progress: str) -> StepResult:
        while True:
            options = self._build_options(state)
            choice = self.backend.get_selection(
                f"Tools  [{progress}]",
                options,
                "Select a tool to configure.",
            )

            if choice is None:
                return StepResult(action=StepAction.CANCEL)
            if choice == BACK_SENTINEL:
                return StepResult(action=StepAction.BACK)
            if choice == "__done":
                return StepResult(action=StepAction.NEXT)
            if choice == "__sep":
                continue

            if choice == "web_search":
                result = self._web_search.run(state, progress)
                if result and result.action == StepAction.NEXT:
                    state.apply(result.data)

    @staticmethod
    def _build_options(state: WizardState) -> list[tuple[str, str, str]]:
        return [
            (BACK_SENTINEL, "← Back", ""),
            (
                "web_search",
                f"  Web Search    Brave API: {'enabled' if state.brave_api_key else 'disabled'}",
                "",
            ),
            ("__sep", "  ──────────────────────────────────────", ""),
            ("__done", "  ✓  Done", ""),
        ]
