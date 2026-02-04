"""Data models for agent execution."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ApprovalMode(str, Enum):
    """Tool execution approval mode."""

    AUTO = "auto"  # All tools execute automatically
    MANUAL = "manual"  # Dangerous tools require approval
    DISABLED = "disabled"  # No tools allowed


class AgentConfig(BaseModel):
    """Configuration for agent execution."""

    approval_mode: ApprovalMode = Field(
        default=ApprovalMode.MANUAL,
        description="Tool approval mode: auto, manual, or disabled",
    )

    max_iterations: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum agent loop iterations",
    )

    enable_tools: bool = Field(
        default=True,
        description="Enable tool use (master switch)",
    )

    allowed_tools: Optional[list[str]] = Field(
        default=None,
        description="Whitelist of allowed tool names (None = all)",
    )

    blocked_tools: Optional[list[str]] = Field(
        default=None,
        description="Blacklist of blocked tool names",
    )

    timeout_per_iteration: int = Field(
        default=300,
        ge=10,
        le=600,
        description="Timeout per iteration in seconds",
    )

    def is_tool_allowed(self, tool_name: str, is_dangerous: bool) -> tuple[bool, str]:
        """Check if a tool is allowed to execute.

        Args:
            tool_name: Name of the tool
            is_dangerous: Whether the tool is dangerous

        Returns:
            Tuple of (allowed, reason) - reason is empty string if allowed
        """
        # Check if tools are enabled
        if not self.enable_tools:
            return False, "Tool use is disabled"

        # Check approval mode
        if self.approval_mode == ApprovalMode.DISABLED:
            return False, "Tool approval mode is disabled"

        # Check if tool is in blocklist
        if self.blocked_tools and tool_name in self.blocked_tools:
            return False, f"Tool '{tool_name}' is blocked"

        # Check if tool is in whitelist (if whitelist exists)
        if self.allowed_tools and tool_name not in self.allowed_tools:
            return False, f"Tool '{tool_name}' not in allowed list"

        # Check if dangerous tool needs approval
        if is_dangerous and self.approval_mode == ApprovalMode.MANUAL:
            return False, f"Dangerous tool '{tool_name}' requires manual approval"

        return True, ""


class EventType(str, Enum):
    """Agent execution event types for streaming."""

    ITERATION_START = "iteration_start"  # New iteration begins
    ITERATION_END = "iteration_end"  # Iteration completes
    TOOL_START = "tool_start"  # Tool execution starts
    TOOL_PROGRESS = "tool_progress"  # Tool execution progress update
    TOOL_COMPLETE = "tool_complete"  # Tool execution completes
    TOOL_ERROR = "tool_error"  # Tool execution fails
    TOOL_APPROVAL_NEEDED = "tool_approval_needed"  # Tool needs user approval
    TOOL_APPROVED = "tool_approved"  # Tool approved by user
    TOOL_DENIED = "tool_denied"  # Tool denied by user
    AI_RESPONSE = "ai_response"  # AI response received
    AGENT_COMPLETE = "agent_complete"  # Agent loop completes


class AgentEvent(BaseModel):
    """Event emitted during agent execution for streaming updates."""

    event_type: EventType = Field(
        description="Type of event"
    )

    iteration: int = Field(
        description="Current iteration number (0-based)"
    )

    tool_name: Optional[str] = Field(
        default=None,
        description="Tool name (for tool events)"
    )

    tool_call_id: Optional[str] = Field(
        default=None,
        description="Tool call ID (for tool events)"
    )

    message: Optional[str] = Field(
        default=None,
        description="Human-readable message describing the event"
    )

    data: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional event data (tool parameters, results, etc.)"
    )

    timestamp: Optional[str] = Field(
        default=None,
        description="ISO format timestamp"
    )

    class Config:
        """Pydantic config."""
        use_enum_values = True
