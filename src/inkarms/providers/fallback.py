"""
Fallback handler for InkArms provider layer.

Manages automatic fallback to alternative providers when primary fails.
"""

import logging
from dataclasses import dataclass, field

from inkarms.providers.exceptions import FailureType, classify_error, should_retry

logger = logging.getLogger(__name__)


@dataclass
class FallbackAttempt:
    """Record of a fallback attempt."""

    provider: str
    error: Exception
    failure_type: FailureType


@dataclass
class FallbackHandler:
    """
    Handles provider fallback logic.

    Manages a chain of fallback providers and tracks which have failed
    during the current request cycle.
    """

    fallback_chain: list[str]
    current_index: int = 0
    failed_providers: set[str] = field(default_factory=set)
    attempts: list[FallbackAttempt] = field(default_factory=list)

    def should_fallback(self, error: Exception) -> bool:
        """
        Determine if we should try fallback provider.

        Args:
            error: The exception that caused the failure.

        Returns:
            True if we should try the next fallback provider.
        """
        failure_type = classify_error(error)

        # Record the attempt
        if self.attempts:
            # Get the provider that just failed
            last_provider = self.attempts[-1].provider if self.attempts else "unknown"
            self.attempts.append(
                FallbackAttempt(
                    provider=last_provider,
                    error=error,
                    failure_type=failure_type,
                )
            )

        # Check if this error type should trigger fallback
        if not should_retry(failure_type):
            logger.debug(f"Not falling back for {failure_type.value} error")
            return False

        # Check if we have more providers to try
        return self.current_index < len(self.fallback_chain)

    def get_next_provider(self) -> str | None:
        """
        Get next provider in fallback chain.

        Returns:
            The next provider model string, or None if chain exhausted.
        """
        while self.current_index < len(self.fallback_chain):
            provider = self.fallback_chain[self.current_index]
            self.current_index += 1

            if provider not in self.failed_providers:
                logger.info(f"Trying fallback provider: {provider}")
                return provider

        logger.warning("Fallback chain exhausted")
        return None

    def mark_failed(self, provider: str, error: Exception) -> None:
        """
        Mark provider as failed for this request cycle.

        Args:
            provider: The provider model string that failed.
            error: The exception that caused the failure.
        """
        self.failed_providers.add(provider)
        failure_type = classify_error(error)
        self.attempts.append(
            FallbackAttempt(
                provider=provider,
                error=error,
                failure_type=failure_type,
            )
        )
        logger.warning(f"Provider {provider} failed with {failure_type.value}: {error}")

    def mark_success(self, provider: str) -> None:
        """
        Mark provider as successful (for logging/metrics).

        Args:
            provider: The provider model string that succeeded.
        """
        logger.debug(f"Provider {provider} succeeded")

    def reset(self) -> None:
        """Reset fallback state for new request."""
        self.current_index = 0
        self.failed_providers.clear()
        self.attempts.clear()

    def get_attempt_summary(self) -> str:
        """
        Get a human-readable summary of fallback attempts.

        Returns:
            Summary string describing what providers were tried.
        """
        if not self.attempts:
            return "No fallback attempts"

        lines = []
        for attempt in self.attempts:
            lines.append(f"  - {attempt.provider}: {attempt.failure_type.value} ({attempt.error})")

        return "Fallback attempts:\n" + "\n".join(lines)

    @property
    def has_more_providers(self) -> bool:
        """Check if there are more providers to try."""
        return self.current_index < len(self.fallback_chain)

    @property
    def total_attempts(self) -> int:
        """Total number of providers attempted."""
        return len(self.attempts)
