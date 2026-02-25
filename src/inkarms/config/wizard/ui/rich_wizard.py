from __future__ import annotations

from typing import TYPE_CHECKING

from inkarms.config.wizard.core import WizardState
from inkarms.config.wizard.engine import WizardEngine
from inkarms.config.wizard.steps import build_steps

if TYPE_CHECKING:
    from inkarms.ui.backends.rich_backend.backend import RichBackend


class RichWizard:
    """Rich UI configuration wizard.

    Delegates all step logic to WizardEngine + the step registry in
    inkarms.config.wizard.steps. To add a new configuration section,
    create a WizardStep subclass and add it to build_steps().
    """

    def __init__(self, backend: RichBackend) -> None:
        self.backend = backend

    def run(self) -> bool:
        """Run the wizard flow. Returns True if config was created or skipped."""
        state = WizardState()
        state.load_existing_config()
        engine = WizardEngine(build_steps(self.backend), state)
        return engine.run()
