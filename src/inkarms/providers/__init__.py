"""
InkArms Provider Layer.

Provides unified access to AI models via LiteLLM with:
- Multi-provider support (OpenAI, Anthropic, Google, Ollama, etc.)
- Automatic fallback chains
- Cost tracking
- Health monitoring
"""

from inkarms.providers.cost import CostTracker, count_text_tokens, count_tokens
from inkarms.providers.exceptions import (
    AllProvidersFailedError,
    AuthenticationError,
    ContextLengthExceededError,
    FailureType,
    InvalidRequestError,
    ModelNotFoundError,
    NetworkError,
    ProviderError,
    RateLimitError,
    ServerError,
    classify_error,
    should_retry,
)
from inkarms.providers.fallback import FallbackAttempt, FallbackHandler
from inkarms.providers.manager import (
    ProviderManager,
    clear_provider_manager,
    get_provider_manager,
)
from inkarms.providers.models import (
    CompletionResponse,
    CostEstimate,
    HealthStatus,
    Message,
    MessageRole,
    ProviderHealth,
    SessionCostSummary,
    SessionUsage,
    StreamChunk,
    TokenUsage,
)

__all__ = [
    # Manager
    "ProviderManager",
    "get_provider_manager",
    "clear_provider_manager",
    # Models
    "Message",
    "MessageRole",
    "CompletionResponse",
    "StreamChunk",
    "TokenUsage",
    "CostEstimate",
    "SessionUsage",
    "SessionCostSummary",
    "HealthStatus",
    "ProviderHealth",
    # Exceptions
    "ProviderError",
    "AuthenticationError",
    "RateLimitError",
    "AllProvidersFailedError",
    "ModelNotFoundError",
    "ContextLengthExceededError",
    "NetworkError",
    "ServerError",
    "InvalidRequestError",
    "FailureType",
    "classify_error",
    "should_retry",
    # Fallback
    "FallbackHandler",
    "FallbackAttempt",
    # Cost
    "CostTracker",
    "count_tokens",
    "count_text_tokens",
]
