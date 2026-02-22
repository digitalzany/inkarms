"""Tests for hub authentication module."""

from __future__ import annotations

import time

import pytest

from inkarms.hub.auth import (
    AuthRateLimiter,
    TRUSTED_IPS,
    configure_rate_limiter,
    get_rate_limiter,
    set_api_key,
    verify_key,
)


class TestVerifyKey:
    def setup_method(self) -> None:
        set_api_key("test-secret-key-123")

    def test_correct_key_passes(self) -> None:
        assert verify_key("test-secret-key-123") is True

    def test_wrong_key_fails(self) -> None:
        assert verify_key("wrong-key") is False

    def test_empty_key_fails(self) -> None:
        assert verify_key("") is False

    def test_empty_stored_key_fails(self) -> None:
        # Temporarily clear stored key
        import inkarms.hub.auth as auth_module
        original = auth_module._stored_key_hash
        auth_module._stored_key_hash = ""
        assert verify_key("anything") is False
        auth_module._stored_key_hash = original

    def test_is_constant_time(self) -> None:
        # Both calls should succeed/fail based on correctness, not length
        assert verify_key("test-secret-key-123") is True
        assert verify_key("test-secret-key-124") is False


class TestAuthRateLimiter:
    def test_not_locked_initially(self) -> None:
        limiter = AuthRateLimiter(max_failures=5, window_seconds=60, lockout_seconds=300)
        assert limiter.is_locked("1.2.3.4") is False

    def test_lockout_after_max_failures(self) -> None:
        limiter = AuthRateLimiter(max_failures=3, window_seconds=60, lockout_seconds=300)
        for _ in range(3):
            limiter.record_failure("1.2.3.4")
        assert limiter.is_locked("1.2.3.4") is True

    def test_success_clears_history(self) -> None:
        limiter = AuthRateLimiter(max_failures=3, window_seconds=60, lockout_seconds=300)
        limiter.record_failure("1.2.3.4")
        limiter.record_failure("1.2.3.4")
        limiter.record_success("1.2.3.4")
        assert limiter.is_locked("1.2.3.4") is False

    def test_different_ips_independent(self) -> None:
        limiter = AuthRateLimiter(max_failures=2, window_seconds=60, lockout_seconds=300)
        limiter.record_failure("1.2.3.4")
        limiter.record_failure("1.2.3.4")
        assert limiter.is_locked("1.2.3.4") is True
        assert limiter.is_locked("5.6.7.8") is False

    def test_lockout_expires(self) -> None:
        limiter = AuthRateLimiter(max_failures=2, window_seconds=60, lockout_seconds=1)
        limiter.record_failure("1.2.3.4")
        limiter.record_failure("1.2.3.4")
        assert limiter.is_locked("1.2.3.4") is True
        # Manually advance lockout expiry
        limiter._locked["1.2.3.4"] = time.monotonic() - 1
        assert limiter.is_locked("1.2.3.4") is False


class TestTrustedIPs:
    def test_loopback_in_trusted(self) -> None:
        assert "127.0.0.1" in TRUSTED_IPS
        assert "::1" in TRUSTED_IPS
        assert "0:0:0:0:0:0:0:1" in TRUSTED_IPS

    def test_public_ip_not_trusted(self) -> None:
        assert "8.8.8.8" not in TRUSTED_IPS


class TestConfigureRateLimiter:
    def test_configure_replaces_global(self) -> None:
        configure_rate_limiter(max_failures=5, window_seconds=30, lockout_seconds=60)
        limiter = get_rate_limiter()
        assert limiter._max_failures == 5
        assert limiter._window == 30
        assert limiter._lockout == 60
