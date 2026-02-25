"""Hub step — enable/configure the always-on Hub daemon (advanced only)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from inkarms.config.wizard.step import BACK_SENTINEL, StepAction, StepResult, WizardStep

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState


class HubStep(WizardStep):
    """Configure the InkArms Hub daemon settings."""

    step_key = "hub"
    modes = ("advanced",)

    def run(self, state: WizardState, progress: str) -> StepResult:
        enable_choice = self._selection_with_back(
            f"Hub Daemon  [{progress}]",
            [
                ("yes", "Enable Hub", "REST + WebSocket API, always-on platforms, cron jobs"),
                ("no", "Disable Hub", "Run InkArms as a simple CLI without the daemon"),
            ],
            "The Hub runs InkArms as a background service (inkarms hub start).",
        )

        if enable_choice is None:
            return StepResult(action=StepAction.CANCEL)
        if enable_choice == BACK_SENTINEL:
            return StepResult(action=StepAction.BACK)

        hub_enabled = enable_choice == "yes"
        port = state.hub_port
        trust_localhost = state.hub_trust_localhost

        if hub_enabled:
            port_result, action = self._collect_port(state.hub_port, progress)
            if action != StepAction.NEXT:
                return StepResult(action=action)
            port = port_result

            trust_choice = self._selection_with_back(
                f"Hub Security  [{progress}]",
                [
                    ("yes", "Trust localhost (Default)", "Local processes can access hub without a key"),
                    ("no", "Require API key", "All clients must provide the hub API key"),
                ],
                "Should local processes access the hub without authentication?",
            )
            if trust_choice is None:
                return StepResult(action=StepAction.CANCEL)
            if trust_choice == BACK_SENTINEL:
                return StepResult(action=StepAction.BACK)
            trust_localhost = trust_choice == "yes"

        return StepResult(
            action=StepAction.NEXT,
            data={
                "hub_enabled": hub_enabled,
                "hub_port": port,
                "hub_trust_localhost": trust_localhost,
            },
        )

    def _collect_port(self, default_port: int, progress: str) -> tuple[int, StepAction]:
        """Prompt for hub port. Returns (port, action)."""
        while True:
            raw = self.backend.get_text_input(
                f"Hub Port  [{progress}]",
                "API server port: ",
                default=str(default_port),
            )
            if raw is None:
                return default_port, StepAction.BACK

            raw = raw.strip()
            try:
                port = int(raw)
                if 1024 <= port <= 65535:
                    return port, StepAction.NEXT
                self.backend.display_error("Port must be between 1024 and 65535.")
            except ValueError:
                self.backend.display_error("Please enter a valid port number.")
