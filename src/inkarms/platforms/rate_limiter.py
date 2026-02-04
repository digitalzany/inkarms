"""Rate limiting for platform messages."""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Optional

from inkarms.platforms.models import PlatformType, PlatformUser

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, user: str, retry_after: float):
        """Initialize exception.

        Args:
            user: User identifier that exceeded limit
            retry_after: Seconds to wait before retrying
        """
        self.user = user
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded for {user}, retry after {retry_after:.1f}s")


class RateLimiter:
    """Token bucket rate limiter for platform messages.

    Uses token bucket algorithm for smooth rate limiting:
    - Each user gets a bucket with max tokens
    - Tokens refill at a steady rate
    - Each message consumes 1 token
    - If no tokens available, request is rate limited
    """

    def __init__(
        self,
        max_tokens: int = 10,
        refill_rate: float = 1.0,
        refill_interval: float = 60.0,
    ):
        """Initialize rate limiter.

        Args:
            max_tokens: Maximum tokens in bucket (burst capacity)
            refill_rate: Number of tokens to add per interval
            refill_interval: Interval in seconds between refills (default: 60s = 1 minute)

        Example:
            max_tokens=10, refill_rate=1, refill_interval=60
            = 10 messages burst, then 1 message per minute
        """
        self._max_tokens = max_tokens
        self._refill_rate = refill_rate
        self._refill_interval = refill_interval

        # User buckets: {user_key: (tokens, last_refill_time)}
        self._buckets: dict[str, tuple[float, float]] = {}

        # Platform limits: {platform: max_per_second}
        self._platform_limits: dict[PlatformType, Optional[float]] = {}

        # Platform counters: {platform: [(timestamp, count), ...]}
        self._platform_counters: dict[PlatformType, list[tuple[float, int]]] = defaultdict(list)

        self._lock = asyncio.Lock()

    def set_platform_limit(self, platform: PlatformType, max_per_second: Optional[float]) -> None:
        """Set rate limit for a specific platform.

        Args:
            platform: Platform type
            max_per_second: Maximum messages per second for this platform (None = no limit)
        """
        self._platform_limits[platform] = max_per_second
        logger.info(f"Set rate limit for {platform.value}: {max_per_second}/s")

    async def check_limit(
        self,
        user: PlatformUser,
        cost: float = 1.0,
    ) -> None:
        """Check if request is within rate limit.

        Args:
            user: Platform user making the request
            cost: Cost in tokens (default: 1.0 for single message)

        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        async with self._lock:
            # Check platform-wide limit first
            await self._check_platform_limit(user.platform)

            # Check per-user limit
            user_key = str(user)
            now = time.time()

            # Get or create bucket
            if user_key not in self._buckets:
                self._buckets[user_key] = (float(self._max_tokens), now)

            tokens, last_refill = self._buckets[user_key]

            # Calculate refills since last check
            time_passed = now - last_refill
            refills = (time_passed / self._refill_interval) * self._refill_rate
            tokens = min(self._max_tokens, tokens + refills)

            # Check if enough tokens
            if tokens < cost:
                # Calculate retry after time
                tokens_needed = cost - tokens
                retry_after = (tokens_needed / self._refill_rate) * self._refill_interval
                raise RateLimitExceeded(user_key, retry_after)

            # Consume tokens
            tokens -= cost
            self._buckets[user_key] = (tokens, now)

            logger.debug(
                f"Rate limit check passed for {user_key}: "
                f"{tokens:.1f}/{self._max_tokens} tokens remaining"
            )

    async def _check_platform_limit(self, platform: PlatformType) -> None:
        """Check platform-wide rate limit.

        Args:
            platform: Platform type

        Raises:
            RateLimitExceeded: If platform limit is exceeded
        """
        limit = self._platform_limits.get(platform)
        if limit is None:
            return

        now = time.time()
        window_start = now - 1.0  # 1 second window

        # Clean up old entries
        counters = self._platform_counters[platform]
        counters[:] = [(ts, count) for ts, count in counters if ts >= window_start]

        # Calculate current rate
        total_messages = sum(count for _, count in counters)

        if total_messages >= limit:
            raise RateLimitExceeded(
                f"platform:{platform.value}",
                retry_after=1.0,
            )

        # Add current request
        counters.append((now, 1))

    async def get_user_status(self, user: PlatformUser) -> dict[str, float]:
        """Get rate limit status for a user.

        Args:
            user: Platform user

        Returns:
            Dict with tokens, max_tokens, refill_rate, refill_interval
        """
        async with self._lock:
            user_key = str(user)
            now = time.time()

            if user_key not in self._buckets:
                return {
                    "tokens": float(self._max_tokens),
                    "max_tokens": float(self._max_tokens),
                    "refill_rate": self._refill_rate,
                    "refill_interval": self._refill_interval,
                }

            tokens, last_refill = self._buckets[user_key]

            # Calculate current tokens with refills
            time_passed = now - last_refill
            refills = (time_passed / self._refill_interval) * self._refill_rate
            current_tokens = min(self._max_tokens, tokens + refills)

            return {
                "tokens": current_tokens,
                "max_tokens": float(self._max_tokens),
                "refill_rate": self._refill_rate,
                "refill_interval": self._refill_interval,
            }

    async def reset_user(self, user: PlatformUser) -> None:
        """Reset rate limit for a user (fill bucket to max).

        Args:
            user: Platform user
        """
        async with self._lock:
            user_key = str(user)
            now = time.time()
            self._buckets[user_key] = (float(self._max_tokens), now)
            logger.info(f"Reset rate limit for {user_key}")

    async def cleanup_old_buckets(self, max_age: float = 3600.0) -> int:
        """Clean up buckets for users not seen recently.

        Args:
            max_age: Maximum age in seconds (default: 1 hour)

        Returns:
            Number of buckets cleaned up
        """
        async with self._lock:
            now = time.time()
            old_buckets = [
                user_key
                for user_key, (_, last_refill) in self._buckets.items()
                if now - last_refill > max_age
            ]

            for user_key in old_buckets:
                del self._buckets[user_key]

            if old_buckets:
                logger.info(f"Cleaned up {len(old_buckets)} old rate limit buckets")

            return len(old_buckets)


# Singleton instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(
    max_tokens: int = 10,
    refill_rate: float = 1.0,
    refill_interval: float = 60.0,
) -> RateLimiter:
    """Get the global rate limiter instance.

    Args:
        max_tokens: Maximum tokens in bucket (only used on first call)
        refill_rate: Tokens to add per interval (only used on first call)
        refill_interval: Refill interval in seconds (only used on first call)

    Returns:
        RateLimiter singleton
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(max_tokens, refill_rate, refill_interval)
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset the global rate limiter instance."""
    global _rate_limiter
    _rate_limiter = None
