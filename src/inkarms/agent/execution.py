"""Tool execution logic."""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from inkarms.audit.logger import get_audit_logger
from inkarms.models.agent import AgentConfig, AgentEvent, ApprovalMode, EventType
from inkarms.models.tools import ToolCall, ToolResult
from inkarms.tools.base import Tool
from inkarms.tools.metrics import get_metrics_tracker
from inkarms.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Handles execution of tool calls."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        config: AgentConfig,
        event_callback: Any | None = None,
        approval_callback: Any | None = None,
    ):
        """Initialize tool executor.

        Args:
            tool_registry: Registry containing available tools.
            config: Agent configuration.
            event_callback: Callback for emitting events.
            approval_callback: Callback for manual approval.
        """
        self.tool_registry = tool_registry
        self.config = config
        self.event_callback = event_callback
        self.approval_callback = approval_callback

    async def execute_batch(self, tool_calls: list[ToolCall], iteration: int) -> list[ToolResult]:
        """Execute multiple tool calls in parallel."""
        if not tool_calls:
            return []

        results = await asyncio.gather(
            *[self._execute_single(call, iteration) for call in tool_calls],
            return_exceptions=False,
        )
        return list(results)

    async def _execute_single(self, tool_call: ToolCall, iteration: int) -> ToolResult:
        """Execute a single tool call with checks and logging."""
        tool = self.tool_registry.get(tool_call.name)

        if not tool:
            return self._handle_tool_not_found(tool_call, iteration)

        # Access Control
        denial = self._check_access(tool_call, tool, iteration)
        if denial:
            return denial

        # Execution
        return await self._run_tool(tool, tool_call, iteration)

    def _handle_tool_not_found(self, tool_call: ToolCall, iteration: int) -> ToolResult:
        """Handle missing tool case."""
        msg = f"Tool '{tool_call.name}' not found"
        logger.warning(msg)
        self._emit_tool_event(EventType.TOOL_ERROR, tool_call.name, tool_call.id, msg, iteration)
        return ToolResult(
            tool_call_id=tool_call.id,
            output="",
            error=msg,
            is_error=True,
        )

    def _check_access(self, tool_call: ToolCall, tool: Tool, iteration: int) -> ToolResult | None:
        """Check if tool execution is allowed."""
        # Check config allowance
        allowed = True
        reason = None

        if self.config.allowed_tools is not None and tool.name not in self.config.allowed_tools:
            allowed = False
            reason = "Not in whitelist"

        if self.config.blocked_tools is not None and tool.name in self.config.blocked_tools:
            allowed = False
            reason = "In blacklist"

        # Manual Approval
        if not allowed and self.config.approval_mode == ApprovalMode.MANUAL and tool.is_dangerous:
            return self._handle_manual_approval(tool_call, tool, reason or "restricted", iteration)

        if not allowed:
            return self._handle_denial(tool_call, reason or "denied", iteration)

        # Check approval for dangerous tools even if allowed by config lists
        if self.config.approval_mode == ApprovalMode.MANUAL and tool.is_dangerous:
            return self._handle_manual_approval(tool_call, tool, "Dangerous tool", iteration)

        return None

    def _handle_denial(self, tool_call: ToolCall, reason: str, iteration: int) -> ToolResult:
        logger.warning(f"Tool denied: {tool_call.name} - {reason}")
        self._emit_tool_event(
            EventType.TOOL_ERROR,
            tool_call.name,
            tool_call.id,
            f"Tool not allowed: {reason}",
            iteration,
        )
        return ToolResult(
            tool_call_id=tool_call.id,
            output="",
            error=f"Tool not allowed: {reason}",
            is_error=True,
        )

    def _handle_manual_approval(
        self, tool_call: ToolCall, tool: Tool, reason: str, iteration: int
    ) -> ToolResult | None:
        """Request manual approval from user."""
        self._emit_tool_event(
            EventType.TOOL_APPROVAL_NEEDED,
            tool.name,
            tool_call.id,
            f"Approval required: {reason}",
            iteration,
            data={"tool_input": tool_call.input},
        )

        if not self.approval_callback:
            return self._handle_denial(tool_call, "No approval callback available", iteration)

        approved = self.approval_callback(tool_call, tool)
        if approved:
            self._emit_tool_event(
                EventType.TOOL_APPROVED,
                tool.name,
                tool_call.id,
                "Approved",
                iteration,
            )
            return None  # Proceed

        self._emit_tool_event(
            EventType.TOOL_DENIED,
            tool.name,
            tool_call.id,
            "User denied",
            iteration,
        )
        get_audit_logger().log_tool_denied(
            tool_name=tool.name,
            tool_call_id=tool_call.id,
            reason="User denied",
        )
        return ToolResult(
            tool_call_id=tool_call.id,
            output="",
            error="Tool execution denied by user",
            is_error=True,
        )

    async def _run_tool(self, tool: Tool, tool_call: ToolCall, iteration: int) -> ToolResult:
        """Run the tool and record metrics."""
        logger.info(f"Executing tool: {tool.name}")
        start_time = time.time()
        audit = get_audit_logger()

        self._emit_tool_event(
            EventType.TOOL_START,
            tool.name,
            tool_call.id,
            "Executing...",
            iteration,
            data={"tool_input": tool_call.input},
        )
        audit.log_tool_start(
            tool_name=tool.name,
            tool_call_id=tool_call.id,
            parameters=tool_call.input,
            is_dangerous=tool.is_dangerous,
        )

        try:
            result = await tool.execute(tool_call_id=tool_call.id, **tool_call.input)
            duration = time.time() - start_time

            self._record_success(tool, tool_call, result, duration, iteration)
            return result

        except Exception as e:
            duration = time.time() - start_time
            return self._record_failure(tool, tool_call, e, duration, iteration)

    def _record_success(
        self, tool: Tool, tool_call: ToolCall, result: ToolResult, duration: float, iteration: int
    ) -> None:
        get_metrics_tracker().record_execution(
            tool_name=tool.name,
            success=not result.is_error,
            execution_time=duration,
            error_message=result.error if result.is_error else None,
        )
        get_audit_logger().log_tool_complete(
            tool_name=tool.name,
            tool_call_id=tool_call.id,
            execution_time=duration,
            output_preview=result.output[:200] if result.output else "",
        )

        if result.is_error:
            self._emit_tool_event(
                EventType.TOOL_ERROR,
                tool.name,
                tool_call.id,
                "Tool failed",
                iteration,
                data={"error": result.error, "execution_time": duration},
            )
        else:
            self._emit_tool_event(
                EventType.TOOL_COMPLETE,
                tool.name,
                tool_call.id,
                "Tool completed",
                iteration,
                data={
                    "output_preview": result.output[:100],
                    "execution_time": duration,
                },
            )

    def _record_failure(
        self, tool: Tool, tool_call: ToolCall, error: Exception, duration: float, iteration: int
    ) -> ToolResult:
        logger.error(f"Tool exception {tool.name}: {error}")
        get_metrics_tracker().record_execution(
            tool_name=tool.name,
            success=False,
            execution_time=duration,
            error_message=str(error),
        )
        get_audit_logger().log_tool_error(
            tool_name=tool.name,
            tool_call_id=tool_call.id,
            execution_time=duration,
            error=str(error),
        )
        self._emit_tool_event(
            EventType.TOOL_ERROR,
            tool.name,
            tool_call.id,
            "Tool exception",
            iteration,
            data={"exception": str(error), "execution_time": duration},
        )
        return ToolResult(
            tool_call_id=tool_call.id,
            output="",
            error=f"Tool execution failed: {error}",
            is_error=True,
        )

    def _emit_tool_event(
        self,
        event_type: EventType,
        tool_name: str,
        tool_call_id: str,
        message: str,
        iteration: int,
        data: dict[str, Any] | None = None,
    ) -> None:
        if self.event_callback:
            event = AgentEvent(
                event_type=event_type,
                iteration=iteration,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                message=message,
                data=data,
                timestamp=datetime.now().isoformat(),
            )
            self.event_callback(event)
