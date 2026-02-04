"""Base classes for tool implementation."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from inkarms.tools.models import ToolParameter, ToolResult


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""

    def __init__(self, message: str, exit_code: Optional[int] = None):
        """Initialize error.

        Args:
            message: Error message
            exit_code: Optional exit code
        """
        super().__init__(message)
        self.exit_code = exit_code


class Tool(ABC):
    """Base class for all tools.

    Tools are actions the AI agent can invoke to perform operations beyond
    text generation. Each tool defines:
    - Name and description (for AI to understand when to use it)
    - Input parameters (JSON schema)
    - Execution logic
    - Safety classification (safe vs dangerous)
    """

    def __init__(self):
        """Initialize the tool."""
        self._validate_definition()

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name (must be unique)."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the tool does (for AI)."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> list[ToolParameter]:
        """List of tool parameters."""
        pass

    @property
    def is_dangerous(self) -> bool:
        """Whether tool requires user approval.

        Safe tools (read-only): Can execute automatically
        Dangerous tools (write/execute): Require approval

        Returns:
            True if tool modifies system state
        """
        return False

    def get_input_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool input.

        Returns:
            JSON schema describing tool parameters
        """
        properties = {}
        required = []

        for param in self.parameters:
            param_schema: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }

            if param.enum:
                param_schema["enum"] = param.enum

            if param.default is not None:
                param_schema["default"] = param.default

            properties[param.name] = param_schema

            if param.required:
                required.append(param.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        """Get complete tool definition for AI provider.

        Returns:
            Tool definition in Anthropic format
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.get_input_schema(),
        }

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters.

        Args:
            **kwargs: Tool parameters

        Returns:
            ToolResult with output or error

        Raises:
            ToolExecutionError: If execution fails critically
        """
        pass

    def validate_input(self, **kwargs) -> None:
        """Validate input parameters.

        Args:
            **kwargs: Tool parameters

        Raises:
            ValueError: If parameters are invalid
        """
        # Check required parameters
        param_names = {p.name for p in self.parameters}
        required_params = {p.name for p in self.parameters if p.required}

        provided = set(kwargs.keys())

        # Allow special internal parameters
        internal_params = {"tool_call_id"}

        # Check for unknown parameters (excluding internal params)
        unknown = provided - param_names - internal_params
        if unknown:
            raise ValueError(f"Unknown parameters: {', '.join(unknown)}")

        # Check for missing required parameters
        missing = required_params - provided
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")

        # Type validation could be added here

    def _validate_definition(self) -> None:
        """Validate tool definition is correct.

        Raises:
            ValueError: If tool definition is invalid
        """
        if not self.name:
            raise ValueError("Tool name cannot be empty")

        if not self.description:
            raise ValueError("Tool description cannot be empty")

        # Validate parameter names are unique
        param_names = [p.name for p in self.parameters]
        if len(param_names) != len(set(param_names)):
            raise ValueError("Parameter names must be unique")

    def __str__(self) -> str:
        """String representation."""
        return f"Tool({self.name})"

    def __repr__(self) -> str:
        """Representation."""
        return f"<Tool name={self.name} dangerous={self.is_dangerous}>"
