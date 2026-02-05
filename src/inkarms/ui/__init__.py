"""
InkArms UI - Pluggable user interface backends.

Supports multiple UI implementations:
- Rich + prompt_toolkit (default) - lightweight, fast
- Textual (optional) - full TUI framework

Usage:
    from inkarms.ui import get_ui_backend

    ui = get_ui_backend()
    ui.run()
"""

from inkarms.ui.factory import get_ui_backend
from inkarms.ui.protocol import UIBackend

__all__ = ["UIBackend", "get_ui_backend"]
