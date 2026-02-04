"""Data models for tool use system."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """Defines a parameter for a tool."""

    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[list[str]] = None  # For restricted choices


class ToolCall(BaseModel):
    """Represents a tool call from the AI."""

    id: str  # Tool use ID for tracking (from AI response)
    name: str  # Tool name
    input: dict[str, Any]  # Tool input parameters

    def __str__(self) -> str:
        """String representation."""
        return f"{self.name}({', '.join(f'{k}={v}' for k, v in self.input.items())})"


class ToolResult(BaseModel):
    """Represents the result of tool execution."""

    tool_call_id: str  # Links to ToolCall.id
    output: str  # Tool output (stdout, return value, etc.)
    error: Optional[str] = None  # Error message if failed
    exit_code: Optional[int] = None  # For command execution
    is_error: bool = False  # Whether execution failed

    def __str__(self) -> str:
        """String representation."""
        if self.is_error:
            return f"Error: {self.error}"
        return self.output[:200] + ("..." if len(self.output) > 200 else "")
