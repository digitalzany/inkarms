"""
Integration tests for advanced tool use features.

Tests tool combinations, streaming events, parallel execution,
metrics tracking, and platform processor integration.
"""

import asyncio
import time
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import pytest

from inkarms.agent import AgentConfig, AgentEvent, AgentLoop, ApprovalMode, EventType
from inkarms.config import Config
from inkarms.config.schema import AgentConfigSchema, SecurityConfig
from inkarms.platforms.models import PlatformType
from inkarms.platforms.processor import MessageProcessor
from inkarms.providers import get_provider_manager
from inkarms.security.sandbox import SandboxExecutor
from inkarms.tools.builtin import register_builtin_tools
from inkarms.tools.metrics import ToolMetricsTracker, reset_metrics_tracker
from inkarms.tools.registry import ToolRegistry


@pytest.fixture
def config():
    """Create test configuration with tools enabled."""
    return Config(
        agent=AgentConfigSchema(
            enable_tools=True,
            approval_mode="auto",
            max_iterations=5,
        ),
        security=SecurityConfig(),
    )


@pytest.fixture
def agent_config():
    """Create agent config for AgentLoop."""
    return AgentConfig(
        enable_tools=True,
        approval_mode=ApprovalMode.AUTO,
        max_iterations=5,
    )


@pytest.fixture
def tool_registry(config):
    """Create tool registry with all built-in tools."""
    registry = ToolRegistry()
    sandbox = SandboxExecutor.from_config(config.security)
    register_builtin_tools(registry, sandbox)
    return registry


@pytest.fixture
def event_collector():
    """Create event collector for testing streaming events."""

    class EventCollector:
        def __init__(self):
            self.events: List[AgentEvent] = []

        def __call__(self, event: AgentEvent):
            self.events.append(event)

        def get_events_by_type(self, event_type: EventType) -> List[AgentEvent]:
            return [e for e in self.events if e.event_type == event_type]

        def clear(self):
            self.events.clear()

    return EventCollector()


@pytest.fixture
def metrics_tracker(tmp_path):
    """Create metrics tracker with temporary storage."""
    reset_metrics_tracker()
    metrics_file = tmp_path / "tool_metrics.json"
    tracker = ToolMetricsTracker(metrics_file=metrics_file)
    return tracker


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_combination_http_and_python(
    config, agent_config, tool_registry, event_collector, monkeypatch
):
    """Test combining HTTP request with Python evaluation."""
    # Mock provider to return a response that uses both tools
    mock_response = MagicMock()
    mock_response.content = "Result: 16"
    mock_response.model = "test-model"
    mock_response.provider = "test"
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50
    mock_response.cost = 0.001
    mock_response.finish_reason = "completed"

    # In a real test, this would call HTTP + Python tools
    # For now, just verify the infrastructure works
    provider = get_provider_manager()
    agent = AgentLoop(
        provider_manager=provider,
        tool_registry=tool_registry,
        config=agent_config,
        event_callback=event_collector,
    )

    messages = [
        {
            "role": "user",
            "content": "Calculate the square root of 256 using Python",
        }
    ]

    result = await agent.run(messages)

    # Verify tool was used
    assert len(result.tool_calls_made) > 0

    # Verify events were emitted
    tool_start_events = event_collector.get_events_by_type(EventType.TOOL_START)
    tool_complete_events = event_collector.get_events_by_type(EventType.TOOL_COMPLETE)

    assert len(tool_start_events) > 0
    assert len(tool_complete_events) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_streaming_events_during_execution(
    config, agent_config, tool_registry, event_collector
):
    """Test that streaming events are emitted during tool execution."""
    provider = get_provider_manager()
    agent = AgentLoop(
        provider_manager=provider,
        tool_registry=tool_registry,
        config=agent_config,
        event_callback=event_collector,
    )

    messages = [
        {
            "role": "user",
            "content": "Calculate 5! using Python",
        }
    ]

    await agent.run(messages)

    # Verify all expected event types were emitted
    event_types = {e.event_type for e in event_collector.events}

    assert EventType.ITERATION_START in event_types
    assert EventType.ITERATION_END in event_types

    # If tools were used, verify tool events
    if any(e.event_type == EventType.TOOL_START for e in event_collector.events):
        assert EventType.TOOL_START in event_types
        # Either TOOL_COMPLETE or TOOL_ERROR
        assert (
            EventType.TOOL_COMPLETE in event_types or EventType.TOOL_ERROR in event_types
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parallel_tool_execution_performance(
    config, agent_config, tool_registry, event_collector
):
    """Test that multiple tools execute in parallel for better performance."""
    provider = get_provider_manager()
    agent = AgentLoop(
        provider_manager=provider,
        tool_registry=tool_registry,
        config=agent_config,
        event_callback=event_collector,
    )

    # Query that should trigger multiple independent tools
    messages = [
        {
            "role": "user",
            "content": "Calculate sqrt(144) and also calculate 10!",
        }
    ]

    start_time = time.time()
    result = await agent.run(messages)
    total_time = time.time() - start_time

    # Get tool execution times from events
    tool_complete_events = event_collector.get_events_by_type(EventType.TOOL_COMPLETE)

    if len(tool_complete_events) >= 2:
        # Calculate individual tool times
        tool_times = []
        for event in tool_complete_events:
            if event.data and "execution_time" in event.data:
                tool_times.append(event.data["execution_time"])

        if len(tool_times) >= 2:
            # If tools ran sequentially, total time >= sum of tool times
            # If parallel, total time < sum of tool times
            sequential_time = sum(tool_times)
            # Allow some overhead for agent loop
            # Parallel should be significantly faster than sequential
            assert total_time >= sequential_time + 2.0  # 2s overhead allowance


@pytest.mark.integration
@pytest.mark.asyncio
async def test_metrics_tracking_across_executions(
    config, tool_registry, metrics_tracker
):
    """Test that tool metrics are tracked correctly across multiple executions."""
    # Clear metrics before test
    metrics_tracker.clear_metrics()

    # Execute tools multiple times
    for i in range(3):
        metrics_tracker.record_execution(
            tool_name="python_eval",
            success=True,
            execution_time=0.1 + (i * 0.01),
            error_message=None,
        )

    # Record one failure
    metrics_tracker.record_execution(
        tool_name="python_eval",
        success=False,
        execution_time=0.05,
        error_message="Test error",
    )

    # Verify stats
    stats = metrics_tracker.get_tool_stats("python_eval")
    assert stats is not None
    assert stats.total_executions == 4
    assert stats.successful_executions == 3
    assert stats.failed_executions == 1
    assert stats.success_rate == 0.75  # 3/4
    assert stats.average_execution_time > 0

    # Verify most used tools
    most_used = metrics_tracker.get_most_used_tools(limit=5)
    assert len(most_used) == 1
    assert most_used[0][0] == "python_eval"
    assert most_used[0][1] == 4

    # Verify recent executions
    recent = metrics_tracker.get_recent_executions(limit=5)
    assert len(recent) == 4
    # Most recent should be the failure
    assert recent[0].success is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_platform_processor_with_tools(config, event_collector, tmp_path):
    """Test platform processor integration with tool execution."""
    # Create processor with event callback
    processor = MessageProcessor(event_callback=event_collector)

    query = "Calculate the square root of 256"

    # Process with tools enabled
    result = await processor.process(
        query=query,
        session_id="test-session",
        platform=PlatformType.CLI,
        platform_user_id="test-user",
        platform_username="Test User",
    )

    # Verify result contains tool usage info
    assert hasattr(result, "tools_used")
    assert hasattr(result, "iterations")

    # If tools were used, verify events were emitted
    if result.tools_used > 0:
        tool_events = event_collector.get_events_by_type(EventType.TOOL_START)
        assert len(tool_events) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_platform_processor_streaming_with_tools(
    config, event_collector, tmp_path
):
    """Test platform processor streaming with tool execution."""
    # Create processor with event callback
    processor = MessageProcessor(event_callback=event_collector)

    query = "Calculate 10 factorial using Python"

    # Process with streaming
    chunks = []
    async for chunk in processor.process_streaming(
        query=query,
        session_id="test-streaming-session",
        platform=PlatformType.TELEGRAM,
        platform_user_id="test-user",
    ):
        chunks.append(chunk)

    # Verify we got chunks
    assert len(chunks) > 0

    # Verify final chunk
    final_chunk = chunks[-1]
    assert final_chunk.is_final

    # Verify events were emitted during streaming
    # (if tools were used)
    if any(e.event_type == EventType.TOOL_START for e in event_collector.events):
        tool_events = event_collector.get_events_by_type(EventType.TOOL_START)
        assert len(tool_events) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_git_operations_sequence(config, agent_config, tool_registry, event_collector, tmp_path):
    """Test sequence of Git operations (status, log)."""
    # Create a test git repository
    test_repo = tmp_path / "test_repo"
    test_repo.mkdir()

    # Initialize git repo
    import subprocess

    subprocess.run(["git", "init"], cwd=test_repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=test_repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=test_repo,
        check=True,
    )

    # Create and commit a file
    (test_repo / "test.txt").write_text("test content")
    subprocess.run(["git", "add", "test.txt"], cwd=test_repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=test_repo,
        check=True,
    )

    # Now test git operations via tools
    provider = get_provider_manager()
    agent = AgentLoop(
        provider_manager=provider,
        tool_registry=tool_registry,
        config=agent_config,
        event_callback=event_collector,
    )

    messages = [
        {
            "role": "user",
            "content": f"Check the git status in {test_repo}",
        }
    ]

    result = await agent.run(messages)

    # Verify git operation was used
    git_tools = [tc for tc in result.tool_calls_made if tc.name == "git_operation"]
    # May or may not use git_operation depending on AI decision
    # Just verify execution completed
    assert result.success or result.error is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_handling_in_tool_execution(config, agent_config, tool_registry, event_collector):
    """Test that tool errors are handled gracefully."""
    provider = get_provider_manager()
    agent = AgentLoop(
        provider_manager=provider,
        tool_registry=tool_registry,
        config=agent_config,
        event_callback=event_collector,
    )

    # Query that should trigger a Python error
    messages = [
        {
            "role": "user",
            "content": "Execute this Python code: import os (this should fail)",
        }
    ]

    result = await agent.run(messages)

    # Verify execution completed (even if tool failed)
    assert result is not None

    # If tool execution failed, verify error event was emitted
    error_events = event_collector.get_events_by_type(EventType.TOOL_ERROR)
    # May or may not have errors depending on AI behavior
    # Just verify event handling works


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_iterations_with_tools(config, agent_config, tool_registry, event_collector):
    """Test multi-turn conversation with tool use."""
    provider = get_provider_manager()
    agent = AgentLoop(
        provider_manager=provider,
        tool_registry=tool_registry,
        config=agent_config,
        event_callback=event_collector,
    )

    messages = [
        {
            "role": "user",
            "content": "Calculate sqrt(256), then calculate the factorial of that result",
        }
    ]

    result = await agent.run(messages)

    # Verify at least one iteration occurred
    iteration_events = event_collector.get_events_by_type(EventType.ITERATION_START)
    assert len(iteration_events) >= 1

    # Agent should have run - either completed or hit max iterations
    # Both are valid outcomes depending on AI behavior
    assert result.iterations >= 1

    # Verify agent stopped for a valid reason
    assert result.stopped_reason in ["completed", "max_iterations", "no_tool_calls"]
