from __future__ import annotations

import io
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from inkarms.ui.protocol import StatusInfo


def render_markdown_ansi(
    text: str,
    width: int = 100,
    style: str = "",
    wrap_in_panel: bool = False,
    panel_title: str | None = None,
    panel_border_style: str = "blue",
) -> str:
    """Render markdown to ANSI-formatted string using Rich."""
    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        width=width,
        color_system="256",
        highlight=False,
    )
    md = Markdown(text, code_theme="monokai", style=style)

    if wrap_in_panel:
        renderable = Panel(
            md,
            title=panel_title,
            style=style,  # Panel content style
            border_style=panel_border_style,
            expand=False,  # Let it fill width
            padding=(0, 1),
        )
    else:
        renderable = md

    console.print(renderable)
    return console.file.getvalue().rstrip()


def render_styled_text(text: str, style_str: str) -> str:
    """Render text with a specific style to ANSI string."""
    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        color_system="256",
    )
    console.print(Text(text, style=style_str), end="")
    return console.file.getvalue()


def build_status_bar(
    status: StatusInfo,
    *,
    agent_config=None,
    tool_registry=None,
    session_manager=None,
    streaming: bool = False,
    separator: str = " | ",
    model_format: str = "short",
) -> list[tuple[str, str]]:
    """Build formatted status bar text from status info.

    Args:
        status: Current status info.
        agent_config: Optional agent config (for tools indicator).
        tool_registry: Optional tool registry (for tool count).
        session_manager: Optional session manager (for context %).
        streaming: If True, show streaming indicator instead.
        separator: Separator string between status items.
        model_format: "short" strips provider prefix, "full" shows provider prefix only.
    """
    if streaming:
        return [("class:info", " Streaming response... | Ctrl+C to cancel ")]

    model = status.model or "—"
    if model_format == "short" and "/" in model:
        model = model.split("/")[1]
    elif model_format == "full" and "/" in model:
        model = model.split("/")[0]

    items: list[tuple[str, str]] = [
        ("class:status-bar", " "),
        ("class:status-provider", f"{status.provider or '—'}"),
        ("class:status-bar", separator),
        ("class:status-model", f"{model}"),
        ("class:status-bar", separator),
        ("class:status-session", f"{status.session or '—'}"),
        ("class:status-bar", f" ({status.message_count})"),
        ("class:status-bar", separator),
        ("class:status-tokens", f"{status.total_tokens:,} tok"),
        ("class:status-bar", separator),
        ("class:status-cost", f"${status.total_cost:.2f}"),
    ]

    # Context usage (when session manager is available)
    if session_manager:
        try:
            usage = session_manager.get_context_usage()
            percent = usage.usage_percent * 100
            ctx_style = "class:warning" if usage.should_compact else "class:status-bar"
            items.extend([
                ("class:status-bar", separator),
                (ctx_style, f"ctx {percent:.0f}%"),
            ])
        except Exception:
            pass

    # Tools indicator
    if agent_config and agent_config.enable_tools:
        tool_count = len(tool_registry) if tool_registry else 0
        mode = agent_config.approval_mode.value
        items.extend([
            ("class:status-bar", separator),
            ("class:tool-running", f"Tools: {tool_count} ({mode})"),
        ])
    elif agent_config is not None:
        items.extend([
            ("class:status-bar", separator),
            ("class:status-bar", "Tools: off"),
        ])

    items.append(("class:status-bar", " "))
    return items
