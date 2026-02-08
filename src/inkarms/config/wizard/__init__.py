"""
InkArms Configuration Wizard.

This package provides both the core logic (state, saving) and UI implementations
(Native Rich/Textual) for the setup wizard.
"""

from inkarms.config.wizard.core import WizardState, save_wizard_config
from inkarms.config.wizard.ui.rich_wizard import RichWizard

__all__ = ["WizardState", "save_wizard_config", "RichWizard"]
