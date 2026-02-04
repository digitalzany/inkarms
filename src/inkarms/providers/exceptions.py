"""
Provider exceptions for InkArms.

Defines custom exceptions for provider-related errors.
"""

from enum import Enum


class FailureType(Enum):
    """Classification of provider failures for fallback decisions."""

    RATE_LIMIT = "rate_limit"
    AUTH_ERROR = "auth_error"
    NETWORK_ERROR = "network_error"
    SERVER_ERROR = "server_error"
    CONTEXT_LENGTH = "context_length"
    INVALID_REQUEST = "invalid_request"
    UNKNOWN = "unknown"


class ProviderError(Exception):
    """Base exception for provider errors."""

    def __init__(self, message: str, provider: str | None = None):
        super().__init__(message)
        self.provider = provider


class AuthenticationError(ProviderError):
    """API key invalid or missing."""

    pass


class RateLimitError(ProviderError):
    """Provider rate limit exceeded."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        retry_after: int | None = None,
    ):
        super().__init__(message, provider)
        self.retry_after = retry_after


class AllProvidersFailedError(ProviderError):
    """All providers in fallback chain failed."""

    def __init__(self, message: str, failed_providers: list[str]):
        super().__init__(message)
        self.failed_providers = failed_providers


class ModelNotFoundError(ProviderError):
    """Requested model not found or not supported."""

    pass


class ContextLengthExceededError(ProviderError):
    """Request exceeded the model's context length."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        max_tokens: int | None = None,
        requested_tokens: int | None = None,
    ):
        super().__init__(message, provider)
        self.max_tokens = max_tokens
        self.requested_tokens = requested_tokens


class NetworkError(ProviderError):
    """Network-related error (connection, timeout, etc.)."""

    pass


class ServerError(ProviderError):
    """Provider server error (5xx status codes)."""

    pass


class InvalidRequestError(ProviderError):
    """Invalid request sent to provider."""

    pass


def classify_error(error: Exception) -> FailureType:
    """
    Classify an exception into a failure type for fallback decisions.

    Args:
        error: The exception to classify.

    Returns:
        The failure type classification.
    """
    # Import LiteLLM exceptions here to avoid circular imports
    try:
        from litellm.exceptions import (
            APIConnectionError,
            APIError,
            AuthenticationError as LiteLLMAuthError,
            ContextWindowExceededError,
            RateLimitError as LiteLLMRateLimitError,
            ServiceUnavailableError,
        )

        if isinstance(error, LiteLLMRateLimitError):
            return FailureType.RATE_LIMIT
        elif isinstance(error, LiteLLMAuthError):
            return FailureType.AUTH_ERROR
        elif isinstance(error, ContextWindowExceededError):
            return FailureType.CONTEXT_LENGTH
        elif isinstance(error, (APIConnectionError, ServiceUnavailableError)):
            return FailureType.NETWORK_ERROR
        elif isinstance(error, APIError):
            # Check status code if available
            status = getattr(error, "status_code", None)
            if status and 500 <= status < 600:
                return FailureType.SERVER_ERROR
            elif status and 400 <= status < 500:
                return FailureType.INVALID_REQUEST
            return FailureType.UNKNOWN
    except ImportError:
        pass

    # Check our own exceptions
    if isinstance(error, RateLimitError):
        return FailureType.RATE_LIMIT
    elif isinstance(error, AuthenticationError):
        return FailureType.AUTH_ERROR
    elif isinstance(error, ContextLengthExceededError):
        return FailureType.CONTEXT_LENGTH
    elif isinstance(error, NetworkError):
        return FailureType.NETWORK_ERROR
    elif isinstance(error, ServerError):
        return FailureType.SERVER_ERROR
    elif isinstance(error, InvalidRequestError):
        return FailureType.INVALID_REQUEST

    return FailureType.UNKNOWN


def should_retry(failure_type: FailureType) -> bool:
    """
    Determine if a failure type should trigger retry/fallback.

    Args:
        failure_type: The classified failure type.

    Returns:
        True if we should try fallback providers.
    """
    # Auth errors should not fallback - user needs to fix config
    # Invalid requests should not fallback - request is malformed
    non_retriable = {
        FailureType.AUTH_ERROR,
        FailureType.INVALID_REQUEST,
    }
    return failure_type not in non_retriable
