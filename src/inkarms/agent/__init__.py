"""Agent execution loop for tool use.

This module provides the agent loop that enables iterative tool execution:
- Parse tool calls from AI responses
- Execute tools through registry
- Feed results back to AI
- Continue until completion
- Stream real-time events during execution
"""

from inkarms.agent.loop import AgentLoop, AgentResult
from inkarms.agent.models import AgentConfig, AgentEvent, ApprovalMode, EventType
from inkarms.agent.parser import ToolCallParser

__all__ = [
    "AgentLoop",
    "AgentResult",
    "AgentConfig",
    "AgentEvent",
    "ApprovalMode",
    "EventType",
    "ToolCallParser",
]
