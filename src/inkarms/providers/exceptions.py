from enum import Enum

from litellm.exceptions import (
            APIConnectionError,
            APIError,
            AuthenticationError as LiteLLMAuthError,
            ContextWindowExceededError as LiteLLMContextWindowExceededError,
            RateLimitError as LiteLLMRateLimitError,
            ServiceUnavailableError as LiteLLMServiceUnavailableError,
)


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
    _exception_map = {
        LiteLLMRateLimitError: FailureType.RATE_LIMIT,
        LiteLLMAuthError: FailureType.AUTH_ERROR,
        LiteLLMContextWindowExceededError: FailureType.CONTEXT_LENGTH,
        APIConnectionError: FailureType.NETWORK_ERROR,
        LiteLLMServiceUnavailableError: FailureType.NETWORK_ERROR,
        RateLimitError: FailureType.RATE_LIMIT,
        AuthenticationError: FailureType.AUTH_ERROR,
        ContextLengthExceededError: FailureType.CONTEXT_LENGTH,
        NetworkError: FailureType.NETWORK_ERROR,
        ServerError: FailureType.SERVER_ERROR,
        InvalidRequestError: FailureType.INVALID_REQUEST,
    }

    if type(error) in _exception_map:
        return _exception_map[type(error)]

    if isinstance(error, APIError):
        status = getattr(error, "status_code", None)
        if status and 500 <= status < 600:
            return FailureType.SERVER_ERROR
        if status and 400 <= status < 500:
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
