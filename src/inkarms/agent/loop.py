"""Agent execution loop for iterative tool use."""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Optional

from inkarms.agent.models import AgentConfig, AgentEvent, ApprovalMode, EventType
from inkarms.agent.parser import ToolCallParser
from inkarms.providers.manager import ProviderManager
from inkarms.tools.base import Tool
from inkarms.tools.metrics import get_metrics_tracker
from inkarms.tools.models import ToolCall, ToolResult
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
    error: Optional[str] = None
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
        config: Optional[AgentConfig] = None,
        approval_callback: Optional[Callable[[ToolCall, Tool], bool]] = None,
        event_callback: Optional[Callable[[AgentEvent], None]] = None,
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
        self.parser = ToolCallParser()

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

    async def run(
        self,
        messages: list[dict[str, Any]],
        model: Optional[str] = None,
    ) -> AgentResult:
        """Run agent loop with tool use.

        Args:
            messages: Conversation messages (OpenAI format)
            model: Optional model override

        Returns:
            AgentResult with final response and execution details
        """
        logger.info("Starting agent loop")

        # Track execution
        iterations = 0
        all_tool_calls: list[ToolCall] = []
        all_tool_results: list[ToolResult] = []
        conversation = messages.copy()

        try:
            # Main agent loop
            while iterations < self.config.max_iterations:
                iterations += 1
                logger.info(f"Agent iteration {iterations}/{self.config.max_iterations}")

                # Emit iteration start event
                self._emit_event(AgentEvent(
                    event_type=EventType.ITERATION_START,
                    iteration=iterations - 1,
                    message=f"Starting iteration {iterations}/{self.config.max_iterations}",
                    timestamp=datetime.now().isoformat(),
                ))

                # Get tool definitions
                tool_definitions = self._get_tool_definitions()

                # Call AI with tools
                try:
                    response = await asyncio.wait_for(
                        self._call_ai(conversation, tool_definitions, model),
                        timeout=self.config.timeout_per_iteration,
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Iteration {iterations} timed out")
                    return AgentResult(
                        success=False,
                        final_response="",
                        iterations=iterations,
                        tool_calls_made=all_tool_calls,
                        tool_results=all_tool_results,
                        error="Iteration timeout",
                        stopped_reason="timeout",
                    )

                # Add assistant response to conversation
                conversation.append(
                    {
                        "role": "assistant",
                        "content": response.get("content"),
                    }
                )

                # Emit AI response event
                self._emit_event(AgentEvent(
                    event_type=EventType.AI_RESPONSE,
                    iteration=iterations - 1,
                    message="AI response received",
                    timestamp=datetime.now().isoformat(),
                ))

                # Check if response contains tool calls
                if not self.parser.has_tool_calls(response):
                    # AI responded without tools - we're done
                    final_text = self.parser.extract_text_content(response)
                    logger.info(f"Agent completed after {iterations} iterations")

                    # Emit completion event
                    self._emit_event(AgentEvent(
                        event_type=EventType.AGENT_COMPLETE,
                        iteration=iterations - 1,
                        message=f"Agent completed after {iterations} iterations",
                        data={"final_response": final_text},
                        timestamp=datetime.now().isoformat(),
                    ))

                    return AgentResult(
                        success=True,
                        final_response=final_text,
                        iterations=iterations,
                        tool_calls_made=all_tool_calls,
                        tool_results=all_tool_results,
                        stopped_reason="completed",
                    )

                # Parse tool calls
                tool_calls = self.parser.parse_response(response)
                if not tool_calls:
                    # No valid tool calls (shouldn't happen if has_tool_calls was True)
                    final_text = self.parser.extract_text_content(response)
                    logger.warning("Response indicated tool use but none found")
                    return AgentResult(
                        success=True,
                        final_response=final_text,
                        iterations=iterations,
                        tool_calls_made=all_tool_calls,
                        tool_results=all_tool_results,
                        stopped_reason="completed",
                    )

                logger.info(f"AI requested {len(tool_calls)} tool calls")

                # Execute tool calls
                tool_results = await self._execute_tool_calls(tool_calls)

                # Track execution
                all_tool_calls.extend(tool_calls)
                all_tool_results.extend(tool_results)

                # Add tool results to conversation
                self._add_tool_results_to_conversation(conversation, tool_results)

                # Emit iteration end event
                self._emit_event(AgentEvent(
                    event_type=EventType.ITERATION_END,
                    iteration=iterations - 1,
                    message=f"Iteration {iterations} completed",
                    data={
                        "tools_executed": len(tool_calls),
                        "tools_succeeded": sum(1 for r in tool_results if not r.is_error),
                    },
                    timestamp=datetime.now().isoformat(),
                ))

            # Max iterations reached
            logger.warning(f"Agent stopped: max iterations ({self.config.max_iterations}) reached")
            return AgentResult(
                success=False,
                final_response="",
                iterations=iterations,
                tool_calls_made=all_tool_calls,
                tool_results=all_tool_results,
                error=f"Maximum iterations ({self.config.max_iterations}) reached",
                stopped_reason="max_iterations",
            )

        except Exception as e:
            logger.error(f"Agent loop error: {e}", exc_info=True)
            return AgentResult(
                success=False,
                final_response="",
                iterations=iterations,
                tool_calls_made=all_tool_calls,
                tool_results=all_tool_results,
                error=str(e),
                stopped_reason="error",
            )

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

        # Return tool definitions
        return [tool.get_tool_definition() for tool in filtered_tools]

    async def _call_ai(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: Optional[str],
    ) -> dict[str, Any]:
        """Call AI provider with tools.

        Args:
            messages: Conversation messages
            tools: Tool definitions
            model: Optional model override

        Returns:
            AI response
        """
        # Convert messages to provider format if needed
        from inkarms.providers.models import Message

        provider_messages = [
            Message(role=msg["role"], content=str(msg["content"]))
            for msg in messages
        ]

        # Use provider manager to complete
        # Note: Tools parameter will be added to ProviderManager in Phase 3
        # For now, we pass it via kwargs which LiteLLM should handle
        result = await self.provider_manager.complete(
            messages=provider_messages,
            model=model,
            stream=False,
            tools=tools if tools else None,
        )

        # Convert response to dict format
        # The result is a CompletionResponse object
        return result.model_dump() if hasattr(result, "model_dump") else dict(result)

    async def _execute_tool_calls(
        self, tool_calls: list[ToolCall]
    ) -> list[ToolResult]:
        """Execute tool calls in parallel.

        All tool calls are executed concurrently using asyncio.gather()
        for maximum performance. Each tool execution is independent.

        Args:
            tool_calls: List of tool calls to execute

        Returns:
            List of tool results (in same order as tool_calls)
        """
        if not tool_calls:
            return []

        # Execute all tools concurrently
        results = await asyncio.gather(
            *[self._execute_single_tool(tool_call) for tool_call in tool_calls],
            return_exceptions=False,  # Let exceptions propagate as ToolResults
        )

        return list(results)

    async def _execute_single_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a single tool call.

        Args:
            tool_call: Tool call to execute

        Returns:
            Tool result
        """
        # Get tool from registry
        tool = self.tool_registry.get(tool_call.name)

        if not tool:
            logger.warning(f"Tool not found: {tool_call.name}")
            self._emit_event(AgentEvent(
                event_type=EventType.TOOL_ERROR,
                iteration=0,
                tool_name=tool_call.name,
                tool_call_id=tool_call.id,
                message=f"Tool '{tool_call.name}' not found",
                timestamp=datetime.now().isoformat(),
            ))
            return ToolResult(
                tool_call_id=tool_call.id,
                output="",
                error=f"Tool '{tool_call.name}' not found",
                is_error=True,
            )

        # Check if tool is allowed
        allowed, reason = self.config.is_tool_allowed(tool.name, tool.is_dangerous)

        # For manual approval mode on dangerous tools, ask for approval
        if not allowed and self.config.approval_mode == ApprovalMode.MANUAL and tool.is_dangerous:
            # Emit approval needed event
            self._emit_event(AgentEvent(
                event_type=EventType.TOOL_APPROVAL_NEEDED,
                iteration=0,
                tool_name=tool.name,
                tool_call_id=tool_call.id,
                message=f"Approval required for tool: {tool.name}",
                data={"tool_input": tool_call.input},
                timestamp=datetime.now().isoformat(),
            ))

            if self.approval_callback:
                approved = self.approval_callback(tool_call, tool)
                if not approved:
                    logger.info(f"Tool execution denied by user: {tool.name}")
                    self._emit_event(AgentEvent(
                        event_type=EventType.TOOL_DENIED,
                        iteration=0,
                        tool_name=tool.name,
                        tool_call_id=tool_call.id,
                        message=f"Tool execution denied: {tool.name}",
                        timestamp=datetime.now().isoformat(),
                    ))
                    return ToolResult(
                        tool_call_id=tool_call.id,
                        output="",
                        error=f"Tool execution denied by user",
                        is_error=True,
                    )
                else:
                    self._emit_event(AgentEvent(
                        event_type=EventType.TOOL_APPROVED,
                        iteration=0,
                        tool_name=tool.name,
                        tool_call_id=tool_call.id,
                        message=f"Tool execution approved: {tool.name}",
                        timestamp=datetime.now().isoformat(),
                    ))
            else:
                # No approval callback provided for manual mode
                logger.warning(f"Manual approval required but no callback: {tool.name}")
                return ToolResult(
                    tool_call_id=tool_call.id,
                    output="",
                    error=f"Manual approval required: {reason}",
                    is_error=True,
                )
        elif not allowed:
            logger.warning(f"Tool not allowed: {tool.name} - {reason}")
            self._emit_event(AgentEvent(
                event_type=EventType.TOOL_ERROR,
                iteration=0,
                tool_name=tool.name,
                tool_call_id=tool_call.id,
                message=f"Tool not allowed: {reason}",
                timestamp=datetime.now().isoformat(),
            ))
            return ToolResult(
                tool_call_id=tool_call.id,
                output="",
                error=f"Tool not allowed: {reason}",
                is_error=True,
            )

        # Emit tool start event
        self._emit_event(AgentEvent(
            event_type=EventType.TOOL_START,
            iteration=0,
            tool_name=tool.name,
            tool_call_id=tool_call.id,
            message=f"Executing tool: {tool.name}",
            data={"tool_input": tool_call.input},
            timestamp=datetime.now().isoformat(),
        ))

        # Execute tool with timing
        logger.info(f"Executing tool: {tool.name}")
        start_time = time.time()

        try:
            result = await tool.execute(tool_call_id=tool_call.id, **tool_call.input)
            execution_time = time.time() - start_time

            # Record metrics
            metrics = get_metrics_tracker()
            metrics.record_execution(
                tool_name=tool.name,
                success=not result.is_error,
                execution_time=execution_time,
                error_message=result.error if result.is_error else None,
            )

            # Emit completion or error event
            if result.is_error:
                self._emit_event(AgentEvent(
                    event_type=EventType.TOOL_ERROR,
                    iteration=0,
                    tool_name=tool.name,
                    tool_call_id=tool_call.id,
                    message=f"Tool failed: {tool.name}",
                    data={"error": result.error, "execution_time": execution_time},
                    timestamp=datetime.now().isoformat(),
                ))
            else:
                self._emit_event(AgentEvent(
                    event_type=EventType.TOOL_COMPLETE,
                    iteration=0,
                    tool_name=tool.name,
                    tool_call_id=tool_call.id,
                    message=f"Tool completed: {tool.name}",
                    data={
                        "output_preview": result.output[:100] if result.output else "",
                        "execution_time": execution_time,
                    },
                    timestamp=datetime.now().isoformat(),
                ))

            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Tool execution failed: {tool.name}: {e}", exc_info=True)

            # Record metrics for exception
            metrics = get_metrics_tracker()
            metrics.record_execution(
                tool_name=tool.name,
                success=False,
                execution_time=execution_time,
                error_message=str(e),
            )

            # Emit error event
            self._emit_event(AgentEvent(
                event_type=EventType.TOOL_ERROR,
                iteration=0,
                tool_name=tool.name,
                tool_call_id=tool_call.id,
                message=f"Tool exception: {tool.name}",
                data={"exception": str(e), "execution_time": execution_time},
                timestamp=datetime.now().isoformat(),
            ))
            return ToolResult(
                tool_call_id=tool_call.id,
                output="",
                error=f"Tool execution failed: {str(e)}",
                is_error=True,
            )

    def _add_tool_results_to_conversation(
        self, conversation: list[dict[str, Any]], tool_results: list[ToolResult]
    ) -> None:
        """Add tool results to conversation.

        Args:
            conversation: Conversation messages (modified in place)
            tool_results: Tool results to add
        """
        # Add tool results as user message with tool_result content
        # This is Anthropic's format for tool results
        for result in tool_results:
            conversation.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": result.tool_call_id,
                            "content": result.output if not result.is_error else None,
                            "is_error": result.is_error,
                        }
                    ],
                }
            )
