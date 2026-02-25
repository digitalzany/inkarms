"""Advanced configuration menu — non-linear section picker (advanced mode only).

Instead of a linear step-by-step flow, advanced mode presents a menu where the
user can enter any section, configure it, and return to the menu.  Sections show
their current values inline so the user can see what's already configured.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from inkarms.config.wizard.core import save_wizard_config
from inkarms.config.wizard.step import StepAction, StepResult, WizardStep
from inkarms.config.wizard.steps.agent import AgentStep
from inkarms.config.wizard.steps.context import ContextStep
from inkarms.config.wizard.steps.cost import CostStep
from inkarms.config.wizard.steps.hub import HubStep
from inkarms.config.wizard.steps.platforms import PlatformsStep
from inkarms.config.wizard.steps.provider import ProviderStep
from inkarms.config.wizard.steps.security import SecurityStep
from inkarms.config.wizard.steps.tools import ToolsStep

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState
    from inkarms.ui.backends.rich_backend.backend import RichBackend

logger = logging.getLogger(__name__)


class AdvancedMenuStep(WizardStep):
    """Non-linear settings menu for advanced mode.

    Loops until the user explicitly selects 'Save & Exit' or cancels with Escape.
    Selecting a section runs that section's step; returning (← Back or Escape
    inside a section) brings the user back to this menu without losing changes.
    """

    step_key = "advanced_menu"
    modes = ("advanced",)

    def __init__(self, backend: RichBackend) -> None:
        super().__init__(backend)
        self._sections: dict[str, WizardStep] = {
            "provider":  ProviderStep(backend),
            "security":  SecurityStep(backend),
            "tools":     ToolsStep(backend),
            "agent":     AgentStep(backend),
            "context":   ContextStep(backend),
            "cost":      CostStep(backend),
            "hub":       HubStep(backend),
            "platforms": PlatformsStep(backend),
        }

    def run(self, state: WizardState, _progress: str) -> StepResult | None:
        while True:
            options = self._build_options(state)
            choice = self.backend.get_selection(
                "Advanced Configuration",
                options,
                "Select a section to configure, or save when done.  Esc to cancel.",
            )

            if choice is None:
                # Escape — cancel without saving
                return StepResult(action=StepAction.CANCEL)

            if choice == "__save":
                try:
                    config_path = save_wizard_config(state)
                    logger.info("Configuration saved to %s", config_path)
                except Exception as e:
                    self.backend.display_error(f"Failed to save configuration: {e}")
                    continue
                return StepResult(action=StepAction.NEXT)

            if choice == "__sep":
                # Separator selected — ignore, redisplay menu
                continue

            step = self._sections.get(choice)
            if step is None:
                continue

            # Run section step; absorb BACK/CANCEL so they return here
            result = step.run(state, choice.title())
            if result.action == StepAction.NEXT:
                state.apply(result.data)

    @staticmethod
    def _build_options(state: WizardState) -> list[tuple[str, str, str]]:
        """Build menu options with current values embedded in labels."""
        enabled_platforms = [
            name for name, cfg in state.platforms.items() if cfg.get("enabled")
        ]
        daily = (
            f"${state.daily_budget:.2f}/day" if state.daily_budget else "no limit"
        )
        hub_val = (
            f"enabled, port {state.hub_port}" if state.hub_enabled else "disabled"
        )
        return [
            (
                "provider",
                f"  Provider      {state.model}  |  discovery: {'on' if state.auto_discover_models else 'off'}",
                "",
            ),
            (
                "security",
                f"  Security      sandbox: {state.sandbox_mode}",
                "",
            ),
            (
                "tools",
                f"  Tools         web search: {'on' if state.brave_api_key else 'off'}",
                "",
            ),
            (
                "agent",
                f"  Agent         {state.approval_mode}, max {state.max_iterations} iters",
                "",
            ),
            (
                "context",
                f"  Context       {state.compaction_strategy} at {state.auto_compact_threshold:.0%}",
                "",
            ),
            (
                "cost",
                f"  Cost          {daily}",
                "",
            ),
            (
                "hub",
                f"  Hub           {hub_val}",
                "",
            ),
            (
                "platforms",
                f"  Platforms     {', '.join(enabled_platforms) or 'none'}",
                "",
            ),
            ("__sep",  "  ──────────────────────────────────────", ""),
            ("__save", "  ✓  Save & Exit", "Save configuration and exit"),
        ]
