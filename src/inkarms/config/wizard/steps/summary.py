"""Summary step — read-only review of all settings, then Confirm & Save or ← Back."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from inkarms.config.wizard.core import save_wizard_config

logger = logging.getLogger(__name__)
from inkarms.config.wizard.step import BACK_SENTINEL, StepAction, StepResult, WizardStep

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState


def _fmt(value: object) -> str:
    """Format a state value for display."""
    if value is None:
        return "not set"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


class SummaryStep(WizardStep):
    """Show a summary of all settings and let the user confirm or go back."""

    step_key = "summary"
    modes = ("quick",)

    def run(self, state: WizardState, progress: str) -> StepResult:
        # Build summary display items
        display_items = self._build_display_items(state)

        # Mix display items with action options
        options = [
            *display_items,
            ("confirm", "✓  Confirm & Save", "Save this configuration"),
        ]

        choice = self._selection_with_back(
            f"Review Configuration  [{progress}]",
            options,
            "Review your settings and confirm to save.",
        )

        if choice is None:
            return StepResult(action=StepAction.CANCEL)
        if choice == BACK_SENTINEL:
            return StepResult(action=StepAction.BACK)
        if choice != "confirm":
            # User picked a display item — ignore, re-show
            return self.run(state, progress)

        # Save
        try:
            config_path = save_wizard_config(state)
            logger.info("Configuration saved to %s", config_path)
        except Exception as e:
            self.backend.display_error(f"Failed to save configuration: {e}")
            return StepResult(action=StepAction.CANCEL)

        return StepResult(action=StepAction.NEXT)

    def _build_display_items(
        self, state: WizardState
    ) -> list[tuple[str, str, str]]:
        """Build a list of (value, label, description) tuples for display."""
        items: list[tuple[str, str, str]] = [
            ("__sep_provider", "── Provider ──────────────────", ""),
            ("__d_provider", f"  Provider:  {state.provider}", ""),
            ("__d_model", f"  Model:     {state.model}", ""),
            ("__d_apikey", f"  API key:   {'set' if state.api_key else 'not set'}", ""),
            ("__sep_sec", "── Security ──────────────────", ""),
            ("__d_sandbox", f"  Sandbox:   {state.sandbox_mode}", ""),
            ("__sep_tools", "── Tools ─────────────────────", ""),
            (
                "__d_brave",
                f"  Web Search:{' enabled' if state.brave_api_key else ' disabled'}",
                "",
            ),
        ]

        if state.mode == "advanced":
            items += [
                ("__sep_agent", "── Agent ──────────────────────", ""),
                ("__d_approval", f"  Approval:  {state.approval_mode}", ""),
                ("__d_iters", f"  Max iters: {state.max_iterations}", ""),
                ("__sep_ctx", "── Context ────────────────────", ""),
                ("__d_compact", f"  Strategy:  {state.compaction_strategy}", ""),
                (
                    "__d_threshold",
                    f"  Threshold: {state.auto_compact_threshold:.0%}",
                    "",
                ),
                ("__sep_cost", "── Cost ───────────────────────", ""),
                (
                    "__d_budget",
                    f"  Budget:    {f'${state.daily_budget:.2f}/day' if state.daily_budget else 'no limit'}",
                    "",
                ),
                ("__d_block", f"  On exceed: {'block' if state.block_on_exceed else 'warn'}", ""),
                ("__sep_hub", "── Hub ────────────────────────", ""),
                (
                    "__d_hub",
                    f"  Hub:       {'enabled (port ' + str(state.hub_port) + ')' if state.hub_enabled else 'disabled'}",
                    "",
                ),
            ]

            enabled_platforms = [
                name for name, cfg in state.platforms.items() if cfg.get("enabled")
            ]
            items.append((
                "__d_platforms",
                f"  Platforms: {', '.join(enabled_platforms) or 'none'}",
                "",
            ))

        return items
