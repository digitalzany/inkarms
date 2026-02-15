"""Agent execution loop for iterative tool use."""

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from inkarms.agent.client import AIClient
from inkarms.agent.definitions import ToolDefinitionBuilder
from inkarms.agent.execution import ToolExecutor
from inkarms.agent.parser import ToolCallParser
from inkarms.models.agent import AgentConfig, AgentEvent, EventType
from inkarms.models.tools import ToolCall, ToolResult
from inkarms.providers.manager import ProviderManager
from inkarms.tools.base import Tool
from inkarms.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_OUTPUT_CHARS = 50_000


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
        stream_callback: Callable[[str], None] | None = None,
    ):
        """Initialize agent loop."""
        self.config = config or AgentConfig()
        self.event_callback = event_callback
        self.approval_callback = approval_callback

        # Initialize sub-components
        self.ai_client = AIClient(provider_manager, stream_callback)
        self.tool_def_builder = ToolDefinitionBuilder(tool_registry, self.config)
        self.tool_executor = ToolExecutor(
            tool_registry=tool_registry,
            config=self.config,
            event_callback=event_callback,
            approval_callback=approval_callback,
        )

    def _emit_event(self, event: AgentEvent) -> None:
        """Emit an event if callback is configured."""
        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception as e:
                logger.warning(f"Event callback error: {e}")

    def _emit_loop_event(
        self,
        event_type: EventType,
        iteration: int,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emit a loop-level event."""
        self._emit_event(
            AgentEvent(
                event_type=event_type,
                iteration=iteration,
                message=message,
                data=data,
                timestamp=datetime.now().isoformat(),
            )
        )

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
        """Run agent loop with tool use."""
        logger.info("Starting agent loop")

        iterations = 0
        all_tool_calls: list[ToolCall] = []
        all_tool_results: list[ToolResult] = []
        conversation = messages.copy()

        try:
            while iterations < self.config.max_iterations:
                iterations += 1
                result = await self._run_iteration(
                    iterations, conversation, all_tool_calls, all_tool_results, model
                )
                if result is not None:
                    return result

            # Max iterations reached
            logger.warning(
                f"Agent stopped: max iterations ({self.config.max_iterations}) reached",
            )
            return self._build_result(
                success=False,
                iterations=iterations,
                all_tool_calls=all_tool_calls,
                all_tool_results=all_tool_results,
                error=f"Maximum iterations ({self.config.max_iterations}) reached",
                stopped_reason="max_iterations",
            )

        except Exception as e:
            logger.debug(f"Agent loop error: {e}")
            return self._build_result(
                success=False,
                iterations=iterations,
                all_tool_calls=all_tool_calls,
                all_tool_results=all_tool_results,
                error=str(e),
                stopped_reason="error",
            )

    async def _run_iteration(
        self,
        iterations: int,
        conversation: list[dict[str, Any]],
        all_tool_calls: list[ToolCall],
        all_tool_results: list[ToolResult],
        model: str | None,
    ) -> AgentResult | None:
        """Run a single agent iteration."""
        iteration_idx = iterations - 1
        logger.info(f"Agent iteration {iterations}/{self.config.max_iterations}")

        self._emit_loop_event(
            EventType.ITERATION_START,
            iteration_idx,
            f"Starting iteration {iterations}/{self.config.max_iterations}",
        )

        # Call AI with tools
        tool_definitions = self.tool_def_builder.build()
        try:
            response = await asyncio.wait_for(
                self.ai_client.call(conversation, tool_definitions, model),
                timeout=self.config.timeout_per_iteration,
            )
        except TimeoutError:
            logger.error(f"Iteration {iterations} timed out")
            return self._build_result(
                success=False,
                iterations=iterations,
                all_tool_calls=all_tool_calls,
                all_tool_results=all_tool_results,
                error="Iteration timeout",
                stopped_reason="timeout",
            )

        # Add assistant response to conversation
        conversation.append({"role": "assistant", "content": response.get("content")})

        self._emit_loop_event(EventType.AI_RESPONSE, iteration_idx, "AI response received")

        # Check if response contains tool calls
        if not ToolCallParser.has_tool_calls(response):
            final_text = ToolCallParser.extract_text_content(response)
            logger.info(f"Agent completed after {iterations} iterations")
            self._emit_loop_event(
                EventType.AGENT_COMPLETE,
                iteration_idx,
                f"Agent completed after {iterations} iterations",
                data={"final_response": final_text},
            )
            return self._build_result(
                success=True,
                final_response=final_text,
                iterations=iterations,
                all_tool_calls=all_tool_calls,
                all_tool_results=all_tool_results,
            )

        # Parse tool calls
        tool_calls = ToolCallParser.parse_response(response)
        if not tool_calls:
            final_text = ToolCallParser.extract_text_content(response)

            # If we had tool calls indicated but failed to parse them, log it
            if ToolCallParser.has_tool_calls(response):
                logger.error(f"Response indicated tool use but parsing failed: {response}")

            # If there's no text AND no tool calls (and parsing failed or wasn't attempted)
            # This is an edge case (empty response)
            if not final_text:
                final_text = "(No content)"

            logger.info("Agent completed iteration without actionable tool calls")
            self._emit_loop_event(
                EventType.AGENT_COMPLETE,
                iteration_idx,
                "Agent completed (no tools to run)",
                data={"final_response": final_text},
            )
            return self._build_result(
                success=True,
                final_response=final_text,
                iterations=iterations,
                all_tool_calls=all_tool_calls,
                all_tool_results=all_tool_results,
            )

        logger.info(f"AI requested {len(tool_calls)} tool calls")

        # Replace the assistant message with OpenAI tool_calls format
        text_content = ToolCallParser.extract_text_content(response)
        conversation[-1] = self._build_tool_call_message(text_content, tool_calls)

        # Execute tool calls and track results
        tool_results = await self.tool_executor.execute_batch(tool_calls, iteration_idx)
        all_tool_calls.extend(tool_calls)
        all_tool_results.extend(tool_results)

        # Add tool results to conversation
        self._add_tool_results_to_conversation(conversation, tool_results)

        self._emit_loop_event(
            EventType.ITERATION_END,
            iteration_idx,
            f"Iteration {iterations} completed",
            data={
                "tools_executed": len(tool_calls),
                "tools_succeeded": sum(1 for r in tool_results if not r.is_error),
            },
        )

        return None  # Continue looping

    @staticmethod
    def _build_tool_call_message(text_content: str, tool_calls: list[ToolCall]) -> dict[str, Any]:
        """Build an assistant message with tool_calls in OpenAI format."""
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
                            json.dumps(tc.input) if isinstance(tc.input, dict) else str(tc.input)
                        ),
                    },
                }
                for tc in tool_calls
            ],
        }

    @staticmethod
    def _truncate_output(output: str, max_chars: int = MAX_TOOL_OUTPUT_CHARS) -> str:
        """Truncate tool output."""
        if len(output) <= max_chars:
            return output
        half = max_chars // 2
        return (
            output[:half]
            + f"\n\n... [truncated {len(output) - max_chars} characters] ...\n\n"
            + output[-half:]
        )

    @staticmethod
    def _add_tool_results_to_conversation(
        conversation: list[dict[str, Any]], tool_results: list[ToolResult]
    ) -> None:
        """Add tool results to conversation in OpenAI format."""
        for result in tool_results:
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "content": (
                        AgentLoop._truncate_output(result.output)
                        if not result.is_error
                        else (result.error or "Error")
                    ),
                }
            )
