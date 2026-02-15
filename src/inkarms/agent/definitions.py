"""Tool definition building logic."""

from typing import Any

from inkarms.models.agent import AgentConfig, ApprovalMode
from inkarms.tools.registry import ToolRegistry


class ToolDefinitionBuilder:
    """Builds tool definitions for AI providers."""

    def __init__(self, tool_registry: ToolRegistry, config: AgentConfig):
        """Initialize builder.

        Args:
            tool_registry: Registry containing available tools.
            config: Agent configuration.
        """
        self.tool_registry = tool_registry
        self.config = config

    def build(self) -> list[dict[str, Any]]:
        """Get tool definitions to send to AI.

        Returns:
            List of tool definitions in OpenAI/Anthropic compatible format.
        """
        if not self.config.enable_tools or self.config.approval_mode == ApprovalMode.DISABLED:
            return []

        all_tools = self.tool_registry.list_tools()
        filtered_tools = []

        for tool in all_tools:
            allowed, _ = self._is_tool_allowed(tool.name, tool.is_dangerous)

            # In manual mode, we expose dangerous tools but gate execution
            if allowed or (self.config.approval_mode == ApprovalMode.MANUAL and tool.is_dangerous):
                filtered_tools.append(tool)

        definitions = []
        for tool in filtered_tools:
            raw = tool.get_tool_definition()
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": raw["name"],
                        "description": raw.get("description", ""),
                        "parameters": raw.get("input_schema", {}),
                    },
                }
            )
        return definitions

    def _is_tool_allowed(self, name: str, is_dangerous: bool) -> tuple[bool, str | None]:
        """Check if tool is allowed by configuration."""
        # 1. Blocked list (highest priority)
        if self.config.blocked_tools and name in self.config.blocked_tools:
            return False, "Tool is explicitly blocked"

        # 2. Allowed list (if present, must be in it)
        if self.config.allowed_tools is not None:
            if name in self.config.allowed_tools:
                return True, None
            return False, "Tool is not in allowlist"

        # 3. Default behavior based on approval mode
        if is_dangerous:
            if self.config.approval_mode == ApprovalMode.DISABLED:
                return False, "Dangerous tools disabled"
            # Manual/Auto modes allow dangerous tools (manual checks at runtime)
            return True, None

        return True, None
