"""
Tool usage metrics tracking.

Tracks tool execution statistics for analytics and optimization.
"""

import json
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from inkarms.storage.paths import get_data_dir


@dataclass
class ToolExecutionMetric:
    """Single tool execution metric."""

    tool_name: str
    success: bool
    execution_time: float  # seconds
    timestamp: float  # unix timestamp
    error_message: Optional[str] = None


@dataclass
class ToolStats:
    """Aggregate statistics for a tool."""

    tool_name: str
    total_executions: int
    successful_executions: int
    failed_executions: int
    total_execution_time: float
    average_execution_time: float
    success_rate: float
    last_used: float  # unix timestamp


class ToolMetricsTracker:
    """Track and analyze tool usage metrics."""

    def __init__(self, metrics_file: Optional[Path] = None):
        """Initialize metrics tracker.

        Args:
            metrics_file: Path to metrics storage file
                         (default: ~/.inkarms/tool_metrics.json)
        """
        if metrics_file is None:
            data_dir = get_data_dir()
            metrics_file = data_dir / "tool_metrics.json"

        self.metrics_file = metrics_file
        self.metrics: list[ToolExecutionMetric] = []
        self._load_metrics()

    def _load_metrics(self) -> None:
        """Load metrics from file."""
        if not self.metrics_file.exists():
            return

        try:
            with open(self.metrics_file, "r") as f:
                data = json.load(f)
                self.metrics = [
                    ToolExecutionMetric(**metric)
                    for metric in data.get("metrics", [])
                ]
        except Exception as e:
            # If loading fails, start fresh
            print(f"Warning: Could not load metrics: {e}")
            self.metrics = []

    def _save_metrics(self) -> None:
        """Save metrics to file."""
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "metrics": [asdict(metric) for metric in self.metrics],
            "last_updated": time.time(),
        }

        with open(self.metrics_file, "w") as f:
            json.dump(data, f, indent=2)

    def record_execution(
        self,
        tool_name: str,
        success: bool,
        execution_time: float,
        error_message: Optional[str] = None,
    ) -> None:
        """Record a tool execution.

        Args:
            tool_name: Name of the tool
            success: Whether execution succeeded
            execution_time: Time taken in seconds
            error_message: Optional error message if failed
        """
        metric = ToolExecutionMetric(
            tool_name=tool_name,
            success=success,
            execution_time=execution_time,
            timestamp=time.time(),
            error_message=error_message,
        )

        self.metrics.append(metric)
        self._save_metrics()

    def get_tool_stats(self, tool_name: str) -> Optional[ToolStats]:
        """Get statistics for a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            ToolStats if tool has been used, None otherwise
        """
        tool_metrics = [m for m in self.metrics if m.tool_name == tool_name]

        if not tool_metrics:
            return None

        total = len(tool_metrics)
        successful = sum(1 for m in tool_metrics if m.success)
        failed = total - successful
        total_time = sum(m.execution_time for m in tool_metrics)
        avg_time = total_time / total if total > 0 else 0
        success_rate = successful / total if total > 0 else 0
        last_used = max(m.timestamp for m in tool_metrics)

        return ToolStats(
            tool_name=tool_name,
            total_executions=total,
            successful_executions=successful,
            failed_executions=failed,
            total_execution_time=total_time,
            average_execution_time=avg_time,
            success_rate=success_rate,
            last_used=last_used,
        )

    def get_all_stats(self) -> list[ToolStats]:
        """Get statistics for all tools.

        Returns:
            List of ToolStats sorted by usage count (descending)
        """
        tool_names = set(m.tool_name for m in self.metrics)
        stats = [self.get_tool_stats(name) for name in tool_names]
        stats = [s for s in stats if s is not None]

        # Sort by total executions (most used first)
        stats.sort(key=lambda s: s.total_executions, reverse=True)

        return stats

    def get_recent_executions(self, limit: int = 10) -> list[ToolExecutionMetric]:
        """Get recent tool executions.

        Args:
            limit: Maximum number of executions to return

        Returns:
            List of recent executions (newest first)
        """
        sorted_metrics = sorted(
            self.metrics,
            key=lambda m: m.timestamp,
            reverse=True
        )
        return sorted_metrics[:limit]

    def get_total_executions(self) -> int:
        """Get total number of tool executions.

        Returns:
            Total execution count
        """
        return len(self.metrics)

    def get_success_rate(self) -> float:
        """Get overall tool success rate.

        Returns:
            Success rate (0.0 to 1.0)
        """
        if not self.metrics:
            return 0.0

        successful = sum(1 for m in self.metrics if m.success)
        return successful / len(self.metrics)

    def get_most_used_tools(self, limit: int = 5) -> list[tuple[str, int]]:
        """Get most frequently used tools.

        Args:
            limit: Maximum number of tools to return

        Returns:
            List of (tool_name, count) tuples
        """
        tool_counts: dict[str, int] = defaultdict(int)

        for metric in self.metrics:
            tool_counts[metric.tool_name] += 1

        sorted_tools = sorted(
            tool_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return sorted_tools[:limit]

    def get_fastest_tools(self, limit: int = 5) -> list[tuple[str, float]]:
        """Get tools with fastest average execution time.

        Args:
            limit: Maximum number of tools to return

        Returns:
            List of (tool_name, avg_time) tuples
        """
        stats = self.get_all_stats()
        sorted_stats = sorted(
            stats,
            key=lambda s: s.average_execution_time
        )

        return [
            (s.tool_name, s.average_execution_time)
            for s in sorted_stats[:limit]
        ]

    def clear_metrics(self) -> None:
        """Clear all metrics."""
        self.metrics = []
        self._save_metrics()


# Global singleton instance
_metrics_tracker: Optional[ToolMetricsTracker] = None


def get_metrics_tracker() -> ToolMetricsTracker:
    """Get global metrics tracker instance.

    Returns:
        ToolMetricsTracker singleton
    """
    global _metrics_tracker
    if _metrics_tracker is None:
        _metrics_tracker = ToolMetricsTracker()
    return _metrics_tracker


def reset_metrics_tracker() -> None:
    """Reset global metrics tracker (for testing)."""
    global _metrics_tracker
    _metrics_tracker = None
