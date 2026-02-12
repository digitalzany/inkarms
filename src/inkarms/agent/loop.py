"""Agent execution loop for iterative tool use."""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from inkarms.agent.parser import ToolCallParser
from inkarms.models.agent import AgentConfig, AgentEvent, ApprovalMode, EventType
from inkarms.models.tools import ToolCall, ToolResult
from inkarms.providers.manager import ProviderManager
from inkarms.tools.base import Tool
from inkarms.tools.metrics import get_metrics_tracker
from inkarms.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Result of agent execution."""

    success: bool
    final_response: str
    iterations: int
    tool_calls_made: list[ToolCall]
    tool_results: list[ToolResult]
    error: str | None = None
    stopped_reason: str = "completed"  # completed, max_iterations, error, timeout


class AgentLoop:
    """Agent execution loop with tool use.

    Orchestrates iterative interaction between AI and tools:
    1. Call AI with available tools
    2. Parse tool calls from response
    3. Execute tools
    4. Feed results back to AI
    5. Repeat until AI responds without tool calls or limit reached
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        tool_registry: ToolRegistry,
        config: AgentConfig | None = None,
        approval_callback: Callable[[ToolCall, Tool], bool] | None = None,
        event_callback: Callable[[AgentEvent], None] | None = None,
    ):
        """Initialize agent loop.

        Args:
            provider_manager: ProviderManager for AI completions
            tool_registry: ToolRegistry with available tools
            config: AgentConfig for execution settings
            approval_callback: Optional callback for manual approval
                               Takes (ToolCall, Tool) and returns bool (approved)
            event_callback: Optional callback for streaming events
                            Takes (AgentEvent) for real-time updates
        """
        self.provider_manager = provider_manager
        self.tool_registry = tool_registry
        self.config = config or AgentConfig()
        self.approval_callback = approval_callback
        self.event_callback = event_callback

    def _emit_event(self, event: AgentEvent) -> None:
        """Emit an event if callback is configured.

        Args:
            event: AgentEvent to emit
        """
        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception as e:
                logger.warning(f"Event callback error: {e}")

    def _emit_tool_event(
        self,
        event_type: EventType,
        tool_name: str,
        tool_call_id: str,
        message: str,
        iteration: int,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emit a tool-related event."""
        self._emit_event(AgentEvent(
            event_type=event_type,
            iteration=iteration,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            message=message,
            data=data,
            timestamp=datetime.now().isoformat(),
        ))

    def _emit_loop_event(
        self,
        event_type: EventType,
        iteration: int,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emit a loop-level event."""
        self._emit_event(AgentEvent(
            event_type=event_type,
            iteration=iteration,
            message=message,
            data=data,
            timestamp=datetime.now().isoformat(),
        ))

    def _build_result(
        self,
        *,
        success: bool,
        iterations: int,
        all_tool_calls: list[ToolCall],
        all_tool_results: list[ToolResult],
        final_response: str = "",
        error: str | None = None,
        stopped_reason: str = "completed",
    ) -> AgentResult:
        """Build an AgentResult with common fields."""
        return AgentResult(
            success=success,
            final_response=final_response,
            iterations=iterations,
            tool_calls_made=all_tool_calls,
            tool_results=all_tool_results,
            error=error,
            stopped_reason=stopped_reason,
        )

    async def run(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
    ) -> AgentResult:
        """Run agent loop with tool use.

        Args:
            messages: Conversation messages (OpenAI format)
            model: Optional model override

        Returns:
            AgentResult with final response and execution details
        """
        logger.info("Starting agent loop")

        iterations = 0
        all_tool_calls: list[ToolCall] = []
        all_tool_results: list[ToolResult] = []
        conversation = messages.copy()

        try:
            while iterations < self.config.max_iterations:
                iterations += 1
                result = await self._run_iteration(
                    iterations, conversation, all_tool_calls, all_tool_results, model,
                )
                if result is not None:
                    return result

            # Max iterations reached
            logger.warning(
                f"Agent stopped: max iterations ({self.config.max_iterations}) reached",
            )
            return self._build_result(
                success=False, iterations=iterations,
                all_tool_calls=all_tool_calls, all_tool_results=all_tool_results,
                error=f"Maximum iterations ({self.config.max_iterations}) reached",
                stopped_reason="max_iterations",
            )

        except Exception as e:
            logger.debug(f"Agent loop error: {e}")
            return self._build_result(
                success=False, iterations=iterations,
                all_tool_calls=all_tool_calls, all_tool_results=all_tool_results,
                error=str(e), stopped_reason="error",
            )

    async def _run_iteration(
        self,
        iterations: int,
        conversation: list[dict[str, Any]],
        all_tool_calls: list[ToolCall],
        all_tool_results: list[ToolResult],
        model: str | None,
    ) -> AgentResult | None:
        """Run a single agent iteration.

        Returns AgentResult if the loop should stop, None to continue.
        """
        iteration_idx = iterations - 1
        logger.info(f"Agent iteration {iterations}/{self.config.max_iterations}")

        self._emit_loop_event(
            EventType.ITERATION_START, iteration_idx,
            f"Starting iteration {iterations}/{self.config.max_iterations}",
        )

        # Call AI with tools
        tool_definitions = self._get_tool_definitions()
        try:
            response = await asyncio.wait_for(
                self._call_ai(conversation, tool_definitions, model),
                timeout=self.config.timeout_per_iteration,
            )
        except TimeoutError:
            logger.error(f"Iteration {iterations} timed out")
            return self._build_result(
                success=False, iterations=iterations,
                all_tool_calls=all_tool_calls, all_tool_results=all_tool_results,
                error="Iteration timeout", stopped_reason="timeout",
            )

        # Add assistant response to conversation
        conversation.append({"role": "assistant", "content": response.get("content")})

        self._emit_loop_event(
            EventType.AI_RESPONSE, iteration_idx, "AI response received",
        )

        # Check if response contains tool calls
        if not ToolCallParser.has_tool_calls(response):
            final_text = ToolCallParser.extract_text_content(response)
            logger.info(f"Agent completed after {iterations} iterations")
            self._emit_loop_event(
                EventType.AGENT_COMPLETE, iteration_idx,
                f"Agent completed after {iterations} iterations",
                data={"final_response": final_text},
            )
            return self._build_result(
                success=True, final_response=final_text, iterations=iterations,
                all_tool_calls=all_tool_calls, all_tool_results=all_tool_results,
            )

        # Parse tool calls
        tool_calls = ToolCallParser.parse_response(response)
        if not tool_calls:
            final_text = ToolCallParser.extract_text_content(response)
            logger.warning("Response indicated tool use but none found")
            return self._build_result(
                success=True, final_response=final_text, iterations=iterations,
                all_tool_calls=all_tool_calls, all_tool_results=all_tool_results,
            )

        logger.info(f"AI requested {len(tool_calls)} tool calls")

        # Replace the assistant message with OpenAI tool_calls format
        # so LiteLLM can pass it correctly on subsequent iterations
        text_content = ToolCallParser.extract_text_content(response)
        conversation[-1] = self._build_tool_call_message(text_content, tool_calls)

        # Execute tool calls and track results
        tool_results = await self._execute_tool_calls(tool_calls, iteration_idx)
        all_tool_calls.extend(tool_calls)
        all_tool_results.extend(tool_results)

        # Add tool results to conversation
        self._add_tool_results_to_conversation(conversation, tool_results)

        self._emit_loop_event(
            EventType.ITERATION_END, iteration_idx,
            f"Iteration {iterations} completed",
            data={
                "tools_executed": len(tool_calls),
                "tools_succeeded": sum(1 for r in tool_results if not r.is_error),
            },
        )

        return None  # Continue looping

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get tool definitions to send to AI.

        Returns:
            List of tool definitions in Anthropic format
        """
        # If tools are disabled, return empty list
        if not self.config.enable_tools or self.config.approval_mode == ApprovalMode.DISABLED:
            return []

        # Get all tools
        all_tools = self.tool_registry.list_tools()

        # Filter based on allowed/blocked lists
        filtered_tools = []
        for tool in all_tools:
            allowed, _ = self.config.is_tool_allowed(tool.name, tool.is_dangerous)

            # For manual approval mode, include dangerous tools in definitions
            # but we'll check approval at execution time
            if allowed or (
                self.config.approval_mode == ApprovalMode.MANUAL and tool.is_dangerous
            ):
                filtered_tools.append(tool)

        # Return tool definitions in OpenAI function calling format
        # (LiteLLM expects this and translates per-provider)
        definitions = []
        for tool in filtered_tools:
            raw = tool.get_tool_definition()
            definitions.append({
                "type": "function",
                "function": {
                    "name": raw["name"],
                    "description": raw.get("description", ""),
                    "parameters": raw.get("input_schema", {}),
                },
            })
        return definitions

    async def _call_ai(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> dict[str, Any]:
        """Call AI provider with tools.

        Args:
            messages: Conversation messages
            tools: Tool definitions
            model: Optional model override

        Returns:
            AI response
        """
        # Call LiteLLM directly with raw dict messages to preserve
        # OpenAI tool fields (tool_calls, tool_call_id) that the Message
        # class would strip. Use provider manager for model resolution
        # and response parsing (cost tracking).
        from litellm import acompletion

        resolved_model = self.provider_manager.resolve_model(model)

        request_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "temperature": 0.7,
            "stream": False,
        }
        if tools:
            request_kwargs["tools"] = tools

        response = await acompletion(**request_kwargs)
        parsed = self.provider_manager.parse_response(response, resolved_model)
        return parsed.model_dump()

    async def _execute_tool_calls(
        self, tool_calls: list[ToolCall], iteration: int,
    ) -> list[ToolResult]:
        """Execute tool calls in parallel.

        All tool calls are executed concurrently using asyncio.gather()
        for maximum performance. Each tool execution is independent.

        Args:
            tool_calls: List of tool calls to execute
            iteration: Current loop iteration (0-indexed)

        Returns:
            List of tool results (in same order as tool_calls)
        """
        if not tool_calls:
            return []

        # Execute all tools concurrently
        results = await asyncio.gather(
            *[
                self._execute_single_tool(tool_call, iteration)
                for tool_call in tool_calls
            ],
            return_exceptions=False,  # Let exceptions propagate as ToolResults
        )

        return list(results)

    async def _execute_single_tool(
        self, tool_call: ToolCall, iteration: int,
    ) -> ToolResult:
        """Execute a single tool call.

        Args:
            tool_call: Tool call to execute
            iteration: Current loop iteration (0-indexed)

        Returns:
            Tool result
        """
        # Get tool from registry
        tool = self.tool_registry.get(tool_call.name)

        if not tool:
            logger.warning(f"Tool not found: {tool_call.name}")
            self._emit_tool_event(
                EventType.TOOL_ERROR, tool_call.name, tool_call.id,
                f"Tool '{tool_call.name}' not found", iteration,
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                output="",
                error=f"Tool '{tool_call.name}' not found",
                is_error=True,
            )

        # Check if tool is allowed to execute
        denial = self._check_tool_access(tool_call, tool, iteration)
        if denial:
            return denial

        # Emit tool start event
        self._emit_tool_event(
            EventType.TOOL_START, tool.name, tool_call.id,
            f"Executing tool: {tool.name}", iteration,
            data={"tool_input": tool_call.input},
        )

        # Execute tool with metrics
        return await self._run_tool(tool, tool_call, iteration)

    def _check_tool_access(
        self, tool_call: ToolCall, tool: Tool, iteration: int,
    ) -> ToolResult | None:
        """Check if tool is allowed to execute.

        Returns error ToolResult if denied, None if allowed.
        """
        allowed, reason = self.config.is_tool_allowed(tool.name, tool.is_dangerous)

        # Manual approval mode: dangerous tools need explicit approval
        if not allowed and self.config.approval_mode == ApprovalMode.MANUAL and tool.is_dangerous:
            return self._handle_manual_approval(tool_call, tool, reason, iteration)

        if not allowed:
            logger.warning(f"Tool not allowed: {tool.name} - {reason}")
            self._emit_tool_event(
                EventType.TOOL_ERROR, tool.name, tool_call.id,
                f"Tool not allowed: {reason}", iteration,
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                output="",
                error=f"Tool not allowed: {reason}",
                is_error=True,
            )

        return None

    def _handle_manual_approval(
        self, tool_call: ToolCall, tool: Tool, reason: str, iteration: int,
    ) -> ToolResult | None:
        """Handle manual approval flow for dangerous tools.

        Returns error ToolResult if denied, None if approved.
        """
        self._emit_tool_event(
            EventType.TOOL_APPROVAL_NEEDED, tool.name, tool_call.id,
            f"Approval required for tool: {tool.name}", iteration,
            data={"tool_input": tool_call.input},
        )

        if not self.approval_callback:
            logger.warning(f"Manual approval required but no callback: {tool.name}")
            return ToolResult(
                tool_call_id=tool_call.id,
                output="",
                error=f"Manual approval required: {reason}",
                is_error=True,
            )

        approved = self.approval_callback(tool_call, tool)
        if approved:
            self._emit_tool_event(
                EventType.TOOL_APPROVED, tool.name, tool_call.id,
                f"Tool execution approved: {tool.name}", iteration,
            )
            return None

        logger.info(f"Tool execution denied by user: {tool.name}")
        self._emit_tool_event(
            EventType.TOOL_DENIED, tool.name, tool_call.id,
            f"Tool execution denied: {tool.name}", iteration,
        )
        return ToolResult(
            tool_call_id=tool_call.id,
            output="",
            error="Tool execution denied by user",
            is_error=True,
        )

    async def _run_tool(
        self, tool: Tool, tool_call: ToolCall, iteration: int,
    ) -> ToolResult:
        """Execute tool, record metrics, and emit result events."""
        logger.info(f"Executing tool: {tool.name}")
        start_time = time.time()

        try:
            result = await tool.execute(tool_call_id=tool_call.id, **tool_call.input)
            execution_time = time.time() - start_time

            # Record metrics
            get_metrics_tracker().record_execution(
                tool_name=tool.name,
                success=not result.is_error,
                execution_time=execution_time,
                error_message=result.error if result.is_error else None,
            )

            # Emit completion or error event
            if result.is_error:
                self._emit_tool_event(
                    EventType.TOOL_ERROR, tool.name, tool_call.id,
                    f"Tool failed: {tool.name}", iteration,
                    data={"error": result.error, "execution_time": execution_time},
                )
            else:
                self._emit_tool_event(
                    EventType.TOOL_COMPLETE, tool.name, tool_call.id,
                    f"Tool completed: {tool.name}", iteration,
                    data={
                        "output_preview": result.output[:100] if result.output else "",
                        "execution_time": execution_time,
                    },
                )

            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.debug(f"Tool execution failed: {tool.name}: {e}")

            # Record metrics for exception
            get_metrics_tracker().record_execution(
                tool_name=tool.name,
                success=False,
                execution_time=execution_time,
                error_message=str(e),
            )

            self._emit_tool_event(
                EventType.TOOL_ERROR, tool.name, tool_call.id,
                f"Tool exception: {tool.name}", iteration,
                data={"exception": str(e), "execution_time": execution_time},
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                output="",
                error=f"Tool execution failed: {e!s}",
                is_error=True,
            )

    @staticmethod
    def _build_tool_call_message(
        text_content: str, tool_calls: list[ToolCall]
    ) -> dict[str, Any]:
        """Build an assistant message with tool_calls in OpenAI format."""
        import json

        return {
            "role": "assistant",
            "content": text_content or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": (
                            json.dumps(tc.input)
                            if isinstance(tc.input, dict)
                            else str(tc.input)
                        ),
                    },
                }
                for tc in tool_calls
            ],
        }

    def _add_tool_results_to_conversation(
        self, conversation: list[dict[str, Any]], tool_results: list[ToolResult]
    ) -> None:
        """Add tool results to conversation in OpenAI format.

        Args:
            conversation: Conversation messages (modified in place)
            tool_results: Tool results to add
        """
        for result in tool_results:
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "content": result.output if not result.is_error else (result.error or "Error"),
                }
            )
