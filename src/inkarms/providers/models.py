"""
Provider data models for InkArms.

Defines unified response and message types used across all providers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MessageRole(str, Enum):
    """Valid message roles."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    """Conversation message."""

    role: str  # "system" | "user" | "assistant"
    content: str
    timestamp: datetime | None = None
    name: str | None = None  # Optional sender name

    def to_dict(self) -> dict[str, Any]:
        """Convert to LiteLLM-compatible dict."""
        result: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            result["name"] = self.name
        return result

    @classmethod
    def system(cls, content: str) -> "Message":
        """Create a system message."""
        return cls(role=MessageRole.SYSTEM.value, content=content)

    @classmethod
    def user(cls, content: str) -> "Message":
        """Create a user message."""
        return cls(role=MessageRole.USER.value, content=content, timestamp=datetime.now())

    @classmethod
    def assistant(cls, content: str) -> "Message":
        """Create an assistant message."""
        return cls(role=MessageRole.ASSISTANT.value, content=content, timestamp=datetime.now())


@dataclass
class StreamChunk:
    """Single chunk from streaming response."""

    content: str
    finish_reason: str | None = None
    model: str | None = None


@dataclass
class TokenUsage:
    """Token usage statistics."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens


@dataclass
class CompletionResponse:
    """Unified completion response from any provider."""

    content: str | list[dict[str, Any]]  # String or structured content blocks (for tool use)
    model: str
    provider: str
    usage: TokenUsage
    cost: float
    finish_reason: str
    created_at: datetime = field(default_factory=datetime.now)

    # Raw response for debugging
    raw: dict[str, Any] | None = None

    def model_dump(self) -> dict[str, Any]:
        """Convert to dict format (for agent loop compatibility)."""
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "usage": {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "total_tokens": self.usage.total_tokens,
            },
            "cost": self.cost,
            "finish_reason": self.finish_reason,
            "created_at": self.created_at.isoformat(),
        }

    @property
    def input_tokens(self) -> int:
        """Shortcut for input token count."""
        return self.usage.input_tokens

    @property
    def output_tokens(self) -> int:
        """Shortcut for output token count."""
        return self.usage.output_tokens


@dataclass
class CostEstimate:
    """Estimated cost before making a request."""

    model: str
    input_tokens: int
    estimated_output_tokens: int
    input_cost: float
    estimated_output_cost: float
    total_estimated: float


@dataclass
class SessionUsage:
    """Aggregated usage for a session by model."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    request_count: int = 0

    def add(self, usage: TokenUsage, cost: float) -> None:
        """Add usage from a completion."""
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.total_cost += cost
        self.request_count += 1


@dataclass
class SessionCostSummary:
    """Cost summary for a session."""

    by_model: dict[str, SessionUsage]
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float


class HealthStatus(str, Enum):
    """Provider health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ProviderHealth:
    """Health check result for a provider."""

    provider: str
    status: HealthStatus
    latency_ms: float | None
    last_check: datetime
    error: str | None = None
