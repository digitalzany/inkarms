import io

from rich.text import Text
from rich.panel import Panel
from rich.console import Console
from rich.markdown import Markdown


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
