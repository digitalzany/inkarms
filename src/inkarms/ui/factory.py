"""
UI Backend Factory - Creates appropriate UI backend based on config and availability.
"""

import logging
from typing import Literal

from inkarms.ui.protocol import UIBackend, UIConfig

logger = logging.getLogger(__name__)

UIBackendType = Literal["auto", "rich", "textual"]


def _is_textual_available() -> bool:
    """Check if Textual is installed."""
    try:
        import textual
        return True
    except ImportError:
        return False


def _is_rich_available() -> bool:
    """Check if Rich and prompt_toolkit are installed."""
    try:
        import prompt_toolkit
        import rich
        return True
    except ImportError:
        return False


def get_ui_backend(
    backend_type: UIBackendType = "auto",
    config: UIConfig | None = None,
) -> UIBackend:
    """Get UI backend based on type and availability.

    Args:
        backend_type: "auto", "rich", or "textual"
        config: Optional UI configuration

    Returns:
        UIBackend instance

    Raises:
        ImportError: If required dependencies are not installed
    """
    config = config or UIConfig()

    if backend_type == "textual":
        if not _is_textual_available():
            raise ImportError(
                "Textual is not installed. Install with: pip install inkarms[textual]"
            )
        from inkarms.ui.textual_backend import TextualBackend
        return TextualBackend(config)

    if backend_type == "rich":
        if not _is_rich_available():
            raise ImportError(
                "Rich or prompt_toolkit is not installed. These are required dependencies."
            )
        from inkarms.ui.rich_backend import RichBackend
        return RichBackend(config)

    # Auto mode: prefer Rich (lighter), fall back to Textual if Rich unavailable
    if backend_type == "auto":
        if _is_rich_available():
            logger.debug("Using Rich+prompt_toolkit UI backend")
            from inkarms.ui.rich_backend import RichBackend
            return RichBackend(config)

        if _is_textual_available():
            logger.debug("Using Textual UI backend")
            from inkarms.ui.textual_backend import TextualBackend
            return TextualBackend(config)

        raise ImportError(
            "No UI backend available. Install prompt_toolkit: pip install prompt_toolkit"
        )

    raise ValueError(f"Unknown backend type: {backend_type}")


def get_available_backends() -> list[str]:
    """Get list of available UI backends."""
    backends = []
    if _is_rich_available():
        backends.append("rich")
    if _is_textual_available():
        backends.append("textual")
    return backends
