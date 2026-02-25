"""Platforms step — two-level menu: platform picker → per-platform field editor.

Adding a new platform:
  1. Create an adapter in platforms/adapters/<name>.py with PLATFORM_KEY,
     DISPLAY_NAME, and WIZARD_FIELDS class attributes.
  2. Register it in platforms/adapters/__init__._ADAPTER_CLASSES.
  That's it — this step picks it up automatically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from inkarms.config.wizard.step import BACK_SENTINEL, StepAction, StepResult, WizardStep
from inkarms.platforms.adapters import ADAPTER_CLASSES

if TYPE_CHECKING:
    from inkarms.config.wizard.core import WizardState
    from inkarms.platforms.adapters.protocol import PlatformAdapter, PlatformField


class PlatformsStep(WizardStep):
    """Two-level platform configuration menu (advanced mode only).

    Top level: pick a platform to configure, or select Done.
    Platform level: toggle enable, edit each WIZARD_FIELD, select Done/Back.
    """

    step_key = "platforms"
    modes = ("advanced",)

    def run(self, state: WizardState, progress: str) -> StepResult:
        # Work with a local copy — only applied to state on Done
        platforms_data: dict[str, dict[str, Any]] = dict(state.platforms)

        while True:
            options = self._platform_picker_options(platforms_data)
            choice = self.backend.get_selection(
                f"Platforms  [{progress}]",
                options,
                "Select a platform to configure.",
            )

            if choice is None:
                return StepResult(action=StepAction.CANCEL)
            if choice == BACK_SENTINEL:
                return StepResult(action=StepAction.BACK)
            if choice == "__done":
                return StepResult(action=StepAction.NEXT, data={"platforms": platforms_data})

            cls = next((c for c in ADAPTER_CLASSES if choice == c.PLATFORM_KEY), None)
            if cls:
                self._configure_platform(cls, platforms_data, progress)

    # ------------------------------------------------------------------
    # Platform picker (top level)
    # ------------------------------------------------------------------

    @staticmethod
    def _platform_picker_options(platforms_data: dict[str, dict[str, Any]]) -> list[tuple[str, str, str]]:
        options: list[tuple[str, str, str]] = [
            (BACK_SENTINEL, "← Back", ""),
        ]
        for cls in ADAPTER_CLASSES:
            pd = platforms_data.get(cls.PLATFORM_KEY, {})
            status = "enabled" if pd.get("enabled") else "disabled"
            options.append((cls.PLATFORM_KEY, f"  {cls.DISPLAY_NAME:<12} {status}", ""))
        options += [
            ("__sep",  "  ──────────────────────────────────────", ""),
            ("__done", "  ✓  Done", ""),
        ]
        return options

    # ------------------------------------------------------------------
    # Per-platform field editor (second level)
    # ------------------------------------------------------------------

    def _configure_platform(
        self,
        cls: type[PlatformAdapter],
        platforms_data: dict[str, dict[str, Any]],
        progress: str,
    ) -> None:
        key = cls.PLATFORM_KEY
        # Start from existing data so edits accumulate across re-entries
        platform_data: dict[str, Any] = dict(platforms_data.get(key, {"enabled": False}))
        label_width = max(len("Enable"), *(len(f.label) for f in cls.WIZARD_FIELDS))

        while True:
            options = self._platform_field_options(cls, platform_data, label_width)
            choice = self.backend.get_selection(
                f"{cls.DISPLAY_NAME}  [{progress}]",
                options,
                "Toggle enable, configure fields, then select Done.",
            )

            if choice is None or choice == "__done":
                platforms_data[key] = platform_data
                return

            if choice == "__enable":
                platform_data["enabled"] = not platform_data.get("enabled", False)
                continue

            if choice == "__sep":
                continue

            field = next((f for f in cls.WIZARD_FIELDS if f.key == choice), None)
            if field:
                self._edit_field(field, platform_data, cls.DISPLAY_NAME, progress)

    @staticmethod
    def _platform_field_options(
        cls: type[PlatformAdapter],
        platform_data: dict[str, Any],
        label_width: int,
    ) -> list[tuple[str, str, str]]:
        enabled = platform_data.get("enabled", False)
        options: list[tuple[str, str, str]] = [
            ("__enable", f"  {'Enable':<{label_width}}  {'yes' if enabled else 'no'}", ""),
        ]
        for f in cls.WIZARD_FIELDS:
            options.append((f.key, f"  {f.label:<{label_width}}  {_display_value(f, platform_data)}", ""))
        options += [
            ("__sep",  "  ──────────────────────────────────────", ""),
            ("__done", "  ← Back to Platforms", ""),
        ]
        return options

    # ------------------------------------------------------------------
    # Field editor
    # ------------------------------------------------------------------

    def _edit_field(
        self,
        field: PlatformField,
        platform_data: dict[str, Any],
        platform_name: str,
        progress: str,
    ) -> None:
        existing = platform_data.get(field.key)
        prompt = f"{field.label} ({field.hint}): " if field.hint else f"{field.label}: "

        if field.input_type == "list":
            existing_str = ", ".join(existing) if existing else ""
            hint_suffix = f" (current: {existing_str})" if existing_str else " (empty = all)"
            raw = self.backend.get_text_input(
                f"{platform_name}  [{progress}]",
                f"{field.label}{hint_suffix}: ",
            )
            if raw is None:
                return
            platform_data[field.key] = [v.strip() for v in raw.split(",") if v.strip()]
        else:
            has_existing = bool(existing)
            full_prompt = prompt + (" (blank to keep existing): " if has_existing else "")
            value = self.backend.get_text_input(
                f"{platform_name}  [{progress}]",
                full_prompt,
                password=(field.input_type == "password"),
            )
            if value is None:
                return
            value = value.strip()
            if not value:
                if has_existing or not field.required:
                    return  # keep existing / leave empty
                self.backend.display_error(f"{field.label} is required.")
                return
            platform_data[field.key] = value


def _display_value(field: PlatformField, platform_data: dict[str, Any]) -> str:
    """Format a field's current value for display in the menu."""
    val = platform_data.get(field.key)
    if field.input_type == "password":
        return "configured" if val else "not set"
    if field.input_type == "list":
        return ", ".join(val) if val else "all"
    return str(val) if val else "not set"
