"""Tests for tool registry."""

import pytest

from inkarms.tools.base import Tool
from inkarms.tools.models import ToolParameter, ToolResult
from inkarms.tools.registry import ToolRegistry, get_tool_registry, reset_tool_registry


class SimpleTool(Tool):
    """Simple safe tool for testing."""

    @property
    def name(self) -> str:
        return "simple_tool"

    @property
    def description(self) -> str:
        return "A simple safe tool"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="input", type="string", description="Input", required=True
            )
        ]

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            tool_call_id=kwargs.get("tool_call_id", "unknown"),
            output="Simple output",
            is_error=False,
        )


class DangerousTool(Tool):
    """Dangerous tool for testing."""

    @property
    def name(self) -> str:
        return "dangerous_tool"

    @property
    def description(self) -> str:
        return "A dangerous tool"

    @property
    def parameters(self) -> list[ToolParameter]:
        return []

    @property
    def is_dangerous(self) -> bool:
        return True

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            tool_call_id=kwargs.get("tool_call_id", "unknown"),
            output="Dangerous output",
            is_error=False,
        )


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_tool(self):
        """Test registering a tool."""
        registry = ToolRegistry()
        tool = SimpleTool()

        registry.register(tool)

        assert len(registry) == 1
        assert "simple_tool" in registry
        assert registry.get("simple_tool") == tool

    def test_register_duplicate_fails(self):
        """Test registering duplicate tool name fails."""
        registry = ToolRegistry()
        tool1 = SimpleTool()
        tool2 = SimpleTool()

        registry.register(tool1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(tool2)

    def test_unregister_tool(self):
        """Test unregistering a tool."""
        registry = ToolRegistry()
        tool = SimpleTool()

        registry.register(tool)
        assert len(registry) == 1

        result = registry.unregister("simple_tool")

        assert result is True
        assert len(registry) == 0
        assert "simple_tool" not in registry

    def test_unregister_nonexistent(self):
        """Test unregistering non-existent tool."""
        registry = ToolRegistry()

        result = registry.unregister("nonexistent")

        assert result is False

    def test_get_tool(self):
        """Test getting a tool by name."""
        registry = ToolRegistry()
        tool = SimpleTool()

        registry.register(tool)

        retrieved = registry.get("simple_tool")
        assert retrieved == tool

    def test_get_nonexistent_tool(self):
        """Test getting non-existent tool returns None."""
        registry = ToolRegistry()

        retrieved = registry.get("nonexistent")
        assert retrieved is None

    def test_list_tools(self):
        """Test listing all tools."""
        registry = ToolRegistry()
        tool1 = SimpleTool()
        tool2 = DangerousTool()

        registry.register(tool1)
        registry.register(tool2)

        tools = registry.list_tools()

        assert len(tools) == 2
        assert tool1 in tools
        assert tool2 in tools

    def test_list_tool_names(self):
        """Test listing all tool names."""
        registry = ToolRegistry()
        tool1 = SimpleTool()
        tool2 = DangerousTool()

        registry.register(tool1)
        registry.register(tool2)

        names = registry.list_tool_names()

        assert len(names) == 2
        assert "simple_tool" in names
        assert "dangerous_tool" in names

    def test_get_tool_definitions(self):
        """Test getting tool definitions for AI provider."""
        registry = ToolRegistry()
        tool = SimpleTool()

        registry.register(tool)

        definitions = registry.get_tool_definitions()

        assert len(definitions) == 1
        assert definitions[0]["name"] == "simple_tool"
        assert definitions[0]["description"] == "A simple safe tool"
        assert "input_schema" in definitions[0]

    def test_get_safe_tools(self):
        """Test filtering safe tools."""
        registry = ToolRegistry()
        safe_tool = SimpleTool()
        dangerous_tool = DangerousTool()

        registry.register(safe_tool)
        registry.register(dangerous_tool)

        safe_tools = registry.get_safe_tools()

        assert len(safe_tools) == 1
        assert safe_tool in safe_tools
        assert dangerous_tool not in safe_tools

    def test_get_dangerous_tools(self):
        """Test filtering dangerous tools."""
        registry = ToolRegistry()
        safe_tool = SimpleTool()
        dangerous_tool = DangerousTool()

        registry.register(safe_tool)
        registry.register(dangerous_tool)

        dangerous_tools = registry.get_dangerous_tools()

        assert len(dangerous_tools) == 1
        assert dangerous_tool in dangerous_tools
        assert safe_tool not in dangerous_tools

    def test_clear(self):
        """Test clearing all tools."""
        registry = ToolRegistry()
        tool1 = SimpleTool()
        tool2 = DangerousTool()

        registry.register(tool1)
        registry.register(tool2)
        assert len(registry) == 2

        registry.clear()

        assert len(registry) == 0
        assert registry.get("simple_tool") is None
        assert registry.get("dangerous_tool") is None

    def test_len(self):
        """Test len() operator."""
        registry = ToolRegistry()

        assert len(registry) == 0

        registry.register(SimpleTool())
        assert len(registry) == 1

        registry.register(DangerousTool())
        assert len(registry) == 2

    def test_contains(self):
        """Test 'in' operator."""
        registry = ToolRegistry()
        tool = SimpleTool()

        assert "simple_tool" not in registry

        registry.register(tool)

        assert "simple_tool" in registry
        assert "nonexistent" not in registry

    def test_str(self):
        """Test string representation."""
        registry = ToolRegistry()
        registry.register(SimpleTool())

        str_repr = str(registry)
        assert "ToolRegistry" in str_repr
        assert "1 tools" in str_repr

    def test_repr(self):
        """Test representation."""
        registry = ToolRegistry()
        registry.register(SimpleTool())
        registry.register(DangerousTool())

        repr_str = repr(registry)
        assert "ToolRegistry" in repr_str
        assert "simple_tool" in repr_str
        assert "dangerous_tool" in repr_str


class TestToolRegistrySingleton:
    """Tests for tool registry singleton."""

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_tool_registry()

    def test_get_tool_registry(self):
        """Test getting global registry."""
        registry1 = get_tool_registry()
        registry2 = get_tool_registry()

        # Should be same instance
        assert registry1 is registry2

    def test_registry_persistence(self):
        """Test registry persists across get_tool_registry calls."""
        registry1 = get_tool_registry()
        registry1.register(SimpleTool())

        registry2 = get_tool_registry()

        assert len(registry2) == 1
        assert "simple_tool" in registry2

    def test_reset_tool_registry(self):
        """Test resetting global registry."""
        registry1 = get_tool_registry()
        registry1.register(SimpleTool())

        reset_tool_registry()

        registry2 = get_tool_registry()

        # Should be a new instance
        assert registry2 is not registry1
        # Should be empty
        assert len(registry2) == 0
