"""
Inkarms - AI Agent CLI Tool

A powerful AI agent CLI with multi-provider support, skills system,
TUI interface, and secure execution sandbox.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("inkarms")
except PackageNotFoundError:
    __version__ = "0.11.0"

__all__ = [
    "__version__",
]
