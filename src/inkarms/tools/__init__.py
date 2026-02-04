"""Tool use system for InkArms agent capabilities.

This module provides the foundation for tool use, enabling the AI agent to:
- Execute bash commands
- Read and write files
- Search files and directories
- Call external APIs
- Perform system operations

All tool execution goes through the security sandbox for safety.
"""

from inkarms.tools.base import Tool, ToolExecutionError
from inkarms.tools.models import ToolCall, ToolParameter, ToolResult
from inkarms.tools.registry import ToolRegistry, get_tool_registry

__all__ = [
    "Tool",
    "ToolExecutionError",
    "ToolCall",
    "ToolParameter",
    "ToolResult",
    "ToolRegistry",
    "get_tool_registry",
]
