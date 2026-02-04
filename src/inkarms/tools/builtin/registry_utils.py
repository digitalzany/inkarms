"""Utility functions for tool registry setup."""

import logging

from inkarms.security.sandbox import SandboxExecutor
from inkarms.tools.builtin.bash import BashTool
from inkarms.tools.builtin.file import ListFilesTool, ReadFileTool, WriteFileTool
from inkarms.tools.builtin.http import HttpRequestTool
from inkarms.tools.builtin.search import SearchFilesTool
from inkarms.tools.registry import ToolRegistry

# Optional tools (require extra dependencies)
try:
    from inkarms.tools.builtin.python import PythonEvalTool
    PYTHON_EVAL_AVAILABLE = True
except ImportError:
    PYTHON_EVAL_AVAILABLE = False

try:
    from inkarms.tools.builtin.git import GitOperationsTool
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False

logger = logging.getLogger(__name__)


def register_builtin_tools(
    registry: ToolRegistry,
    sandbox: SandboxExecutor | None = None,
) -> None:
    """Register all built-in tools.

    Args:
        registry: ToolRegistry to register tools in
        sandbox: Optional SandboxExecutor for bash tool
    """
    # File tools (safe)
    registry.register(ReadFileTool())
    registry.register(ListFilesTool())
    registry.register(SearchFilesTool())

    # File write tool (dangerous)
    registry.register(WriteFileTool())

    # Bash tool (dangerous)
    registry.register(BashTool(sandbox=sandbox))

    # HTTP request tool (dangerous)
    registry.register(HttpRequestTool())

    # Python eval tool (dangerous, optional)
    tools_count = 6
    if PYTHON_EVAL_AVAILABLE:
        registry.register(PythonEvalTool())
        tools_count += 1
        logger.debug("Registered Python eval tool (requires RestrictedPython)")

    # Git operations tool (dangerous, optional)
    if GIT_AVAILABLE:
        registry.register(GitOperationsTool())
        tools_count += 1
        logger.debug("Registered Git operations tool (requires GitPython)")

    logger.info(f"Registered {tools_count} built-in tools")
