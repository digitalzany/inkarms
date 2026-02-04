"""Unit tests for platform rate limiter."""

import asyncio
import pytest
import time

from inkarms.platforms.models import PlatformType, PlatformUser
from inkarms.platforms.rate_limiter import (
    RateLimitExceeded,
    RateLimiter,
    get_rate_limiter,
    reset_rate_limiter,
)


class TestRateLimiter:
    """Tests for RateLimiter class."""

    @pytest.fixture
    def limiter(self):
        """Create a rate limiter for testing."""
        return RateLimiter(max_tokens=10, refill_rate=1.0, refill_interval=60.0)

    @pytest.fixture
    def user(self):
        """Create a test user."""
        return PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123456789",
            username="test_user",
        )

    @pytest.mark.asyncio
    async def test_check_limit_first_time(self, limiter, user):
        """Test check_limit for first-time user."""
        # Should succeed (creates bucket)
        await limiter.check_limit(user)

        # User should now have a bucket
        user_key = str(user)
        assert user_key in limiter._buckets

    @pytest.mark.asyncio
    async def test_check_limit_consumes_token(self, limiter, user):
        """Test that check_limit consumes a token."""
        await limiter.check_limit(user)

        status = await limiter.get_user_status(user)
        # Should have consumed 1 token (10 - 1 = 9)
        assert status["tokens"] < 10

    @pytest.mark.asyncio
    async def test_check_limit_raises_when_exceeded(self, limiter, user):
        """Test that check_limit raises exception when limit exceeded."""
        # Consume all tokens
        for _ in range(10):
            await limiter.check_limit(user)

        # Next one should raise
        with pytest.raises(RateLimitExceeded) as exc_info:
            await limiter.check_limit(user)

        assert "Rate limit exceeded" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_different_users_separate_limits(self, limiter):
        """Test that different users have separate rate limits."""
        user1 = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="111",
        )
        user2 = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="222",
        )

        # Exhaust user1's tokens
        for _ in range(10):
            await limiter.check_limit(user1)

        # user2 should still have tokens
        await limiter.check_limit(user2)

        # user1 should be rate limited
        with pytest.raises(RateLimitExceeded):
            await limiter.check_limit(user1)

    @pytest.mark.asyncio
    async def test_different_platforms_separate_limits(self, limiter):
        """Test that different platforms have separate rate limits."""
        user1 = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123",
        )
        user2 = PlatformUser(
            platform=PlatformType.SLACK,
            platform_user_id="123",  # Same ID, different platform
        )

        # Exhaust user1's tokens
        for _ in range(10):
            await limiter.check_limit(user1)

        # user2 should still have tokens (different platform)
        await limiter.check_limit(user2)

    @pytest.mark.asyncio
    async def test_get_user_status(self, limiter, user):
        """Test getting user status."""
        # Before any check
        status = await limiter.get_user_status(user)

        assert status["tokens"] == 10
        assert status["max_tokens"] == 10
        assert status["refill_rate"] == 1.0
        assert status["refill_interval"] == 60.0

        # After one check
        await limiter.check_limit(user)

        status = await limiter.get_user_status(user)
        assert status["tokens"] < 10

    @pytest.mark.asyncio
    async def test_get_user_status_for_new_user(self, limiter, user):
        """Test getting status for user without bucket."""
        status = await limiter.get_user_status(user)

        # Should return max tokens
        assert status["tokens"] == 10

    @pytest.mark.asyncio
    async def test_reset_user(self, limiter, user):
        """Test resetting a user's rate limit."""
        # Consume some tokens
        await limiter.check_limit(user)
        await limiter.check_limit(user)

        status1 = await limiter.get_user_status(user)
        assert status1["tokens"] < 10

        # Reset
        await limiter.reset_user(user)

        # Should be back to max
        status2 = await limiter.get_user_status(user)
        assert status2["tokens"] == 10

    @pytest.mark.asyncio
    async def test_cleanup_old_buckets(self, limiter):
        """Test cleaning up old buckets."""
        user1 = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="111",
        )
        user2 = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="222",
        )

        # Create buckets for both users
        await limiter.check_limit(user1)
        await limiter.check_limit(user2)

        # Manually age user1's bucket
        user1_key = str(user1)
        tokens, _ = limiter._buckets[user1_key]
        limiter._buckets[user1_key] = (tokens, time.time() - 7200)  # 2 hours ago

        # Cleanup buckets older than 1 hour
        cleaned = await limiter.cleanup_old_buckets(max_age=3600.0)

        assert cleaned == 1
        assert user1_key not in limiter._buckets
        assert str(user2) in limiter._buckets

    @pytest.mark.asyncio
    async def test_set_platform_limit(self, limiter):
        """Test setting platform-wide limit."""
        limiter.set_platform_limit(PlatformType.TELEGRAM, max_per_second=5.0)

        assert limiter._platform_limits[PlatformType.TELEGRAM] == 5.0

    @pytest.mark.asyncio
    async def test_platform_limit_enforced(self, limiter):
        """Test that platform limit is enforced."""
        # Set very low platform limit
        limiter.set_platform_limit(PlatformType.TELEGRAM, max_per_second=2.0)

        user1 = PlatformUser(platform=PlatformType.TELEGRAM, platform_user_id="111")
        user2 = PlatformUser(platform=PlatformType.TELEGRAM, platform_user_id="222")
        user3 = PlatformUser(platform=PlatformType.TELEGRAM, platform_user_id="333")

        # First two should succeed
        await limiter.check_limit(user1)
        await limiter.check_limit(user2)

        # Third should fail (platform limit)
        with pytest.raises(RateLimitExceeded) as exc_info:
            await limiter.check_limit(user3)

        assert "platform:telegram" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cost_parameter(self, limiter, user):
        """Test using custom cost parameter."""
        # Consume 5 tokens at once
        await limiter.check_limit(user, cost=5.0)

        status = await limiter.get_user_status(user)
        # Should have consumed 5 tokens (10 - 5 = 5), allow small floating point error
        assert abs(status["tokens"] - 5.0) < 0.01


class TestRateLimiterSingleton:
    """Tests for rate limiter singleton functions."""

    def test_get_rate_limiter_default(self):
        """Test getting rate limiter with default settings."""
        reset_rate_limiter()  # Ensure clean state

        limiter = get_rate_limiter()

        assert isinstance(limiter, RateLimiter)
        assert limiter._max_tokens == 10
        assert limiter._refill_rate == 1.0
        assert limiter._refill_interval == 60.0

    def test_get_rate_limiter_custom(self):
        """Test getting rate limiter with custom settings."""
        reset_rate_limiter()

        limiter = get_rate_limiter(
            max_tokens=20,
            refill_rate=2.0,
            refill_interval=30.0,
        )

        assert limiter._max_tokens == 20
        assert limiter._refill_rate == 2.0
        assert limiter._refill_interval == 30.0

    def test_get_rate_limiter_singleton(self):
        """Test that get_rate_limiter returns singleton."""
        reset_rate_limiter()

        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()

        # Should be same instance
        assert limiter1 is limiter2

    def test_reset_rate_limiter(self):
        """Test that reset creates new instance."""
        reset_rate_limiter()

        limiter1 = get_rate_limiter()

        reset_rate_limiter()

        limiter2 = get_rate_limiter()

        # Should be different instances
        assert limiter1 is not limiter2


class TestRateLimitExceeded:
    """Tests for RateLimitExceeded exception."""

    def test_exception_creation(self):
        """Test creating exception."""
        exc = RateLimitExceeded("telegram:123", retry_after=60.0)

        assert exc.user == "telegram:123"
        assert exc.retry_after == 60.0
        assert "Rate limit exceeded" in str(exc)
        assert "telegram:123" in str(exc)

    def test_exception_with_different_retry(self):
        """Test exception with different retry_after."""
        exc = RateLimitExceeded("slack:U123", retry_after=30.5)

        assert exc.retry_after == 30.5
        assert "30.5s" in str(exc)
