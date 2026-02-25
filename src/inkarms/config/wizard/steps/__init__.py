"""
Wizard step registry.

Steps are registered in the order they should appear in the wizard.
The engine filters by is_applicable(state) after the WelcomeStep sets the mode.

To add a new step to quick mode:
  1. Create steps/<your_step>.py with a WizardStep subclass (modes = ("quick",)).
  2. Add one line to build_steps() below.

To add a new section to advanced mode:
  1. Create steps/<your_step>.py with a WizardStep subclass.
  2. Add it to AdvancedMenuStep._sections in steps/advanced_menu.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from inkarms.config.wizard.steps.advanced_menu import AdvancedMenuStep
from inkarms.config.wizard.steps.provider import ProviderStep
from inkarms.config.wizard.steps.security import SecurityStep
from inkarms.config.wizard.steps.summary import SummaryStep
from inkarms.config.wizard.steps.tool_secrets import ToolSecretsStep
from inkarms.config.wizard.steps.welcome import WelcomeStep

if TYPE_CHECKING:
    from inkarms.config.wizard.step import WizardStep
    from inkarms.ui.backends.rich_backend.backend import RichBackend


def build_steps(backend: RichBackend) -> list[WizardStep]:
    """Return the ordered list of all top-level wizard steps.

    Step order and mode applicability:

        WelcomeStep       — quick + advanced  (sets mode, recomputes active list)

        Quick mode (linear):
            ProviderStep      — quick only
            SecurityStep      — quick only
            ToolSecretsStep   — quick only
            SummaryStep       — quick only

        Advanced mode (menu-driven):
            AdvancedMenuStep  — advanced only  (loops internally; handles save)
    """
    return [
        WelcomeStep(backend),
        # Quick mode — linear steps
        ProviderStep(backend),
        SecurityStep(backend),
        ToolSecretsStep(backend),
        SummaryStep(backend),
        # Advanced mode — single menu step that handles all sections
        AdvancedMenuStep(backend),
    ]


__all__ = ["build_steps"]
