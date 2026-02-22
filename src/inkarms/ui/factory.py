"""
UI Backend Factory - Creates appropriate UI backend based on config and availability.
"""

import logging
from typing import Literal

from inkarms.ui.protocol import UIBackend, UIConfig

logger = logging.getLogger(__name__)

UIBackendType = Literal["auto", "rich"]


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
        backend_type: "auto" or "rich"
        config: Optional UI configuration

    Returns:
        UIBackend instance

    Raises:
        ImportError: If required dependencies are not installed
    """
    config = config or UIConfig()

    if backend_type in ("rich", "auto"):
        if not _is_rich_available():
            raise ImportError(
                "Rich or prompt_toolkit is not installed. These are required dependencies."
            )
        from inkarms.ui.backends.rich_backend.backend import RichBackend
        return RichBackend(config)

    raise ValueError(f"Unknown backend type: {backend_type}")
