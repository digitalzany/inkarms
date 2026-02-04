"""Tool registry for managing available tools."""

import logging
from typing import Optional

from inkarms.tools.base import Tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for managing available tools.

    The registry maintains a collection of tools that can be invoked by
    the AI agent. Tools can be registered, retrieved, and listed.
    """

    def __init__(self):
        """Initialize the tool registry."""
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool.

        Args:
            tool: Tool instance to register

        Raises:
            ValueError: If tool name already registered
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")

        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def unregister(self, name: str) -> bool:
        """Unregister a tool.

        Args:
            name: Tool name to unregister

        Returns:
            True if tool was unregistered, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Unregistered tool: {name}")
            return True
        return False

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """Get list of all registered tools.

        Returns:
            List of all tools
        """
        return list(self._tools.values())

    def list_tool_names(self) -> list[str]:
        """Get list of all registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def get_tool_definitions(self) -> list[dict]:
        """Get tool definitions for all registered tools.

        Returns tool definitions in format suitable for AI provider.

        Returns:
            List of tool definitions
        """
        return [tool.get_tool_definition() for tool in self._tools.values()]

    def get_safe_tools(self) -> list[Tool]:
        """Get list of safe (non-dangerous) tools.

        Returns:
            List of safe tools
        """
        return [tool for tool in self._tools.values() if not tool.is_dangerous]

    def get_dangerous_tools(self) -> list[Tool]:
        """Get list of dangerous tools.

        Returns:
            List of dangerous tools
        """
        return [tool for tool in self._tools.values() if tool.is_dangerous]

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()
        logger.info("Cleared all tools from registry")

    def __len__(self) -> int:
        """Get number of registered tools."""
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """Check if tool is registered."""
        return name in self._tools

    def __str__(self) -> str:
        """String representation."""
        return f"ToolRegistry({len(self._tools)} tools)"

    def __repr__(self) -> str:
        """Representation."""
        tools = ", ".join(self._tools.keys())
        return f"<ToolRegistry tools=[{tools}]>"


# Global registry instance
_tool_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry instance.

    Returns:
        ToolRegistry singleton
    """
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry


def reset_tool_registry() -> None:
    """Reset the global tool registry instance.

    Useful for testing.
    """
    global _tool_registry
    _tool_registry = None
