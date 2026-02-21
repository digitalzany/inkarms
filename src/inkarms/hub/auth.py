"""
Hub API key authentication middleware.

HTTP auth: Authorization: Bearer <key>  or  X-InkArms-Key: <key>
WS auth:   first message {"type": "auth", "token": "<key>"} within 5 seconds

Keys are compared using hmac.compare_digest() (constant-time) against a
SHA-256 hash of the stored key — prevents timing attacks.

Trusted IPs (127.0.0.1, ::1, 0:0:0:0:0:0:0:1) bypass key checks when
trust_localhost=True. Set trust_localhost=False on shared/cloud systems.

Auth failure rate limiting uses an in-memory sliding window (distinct from
the platform RateLimiter). State resets on hub restart — acceptable for
personal use, documented as a known limitation.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trusted localhost addresses
# ---------------------------------------------------------------------------

TRUSTED_IPS: frozenset[str] = frozenset({"127.0.0.1", "::1", "0:0:0:0:0:0:0:1"})

# ---------------------------------------------------------------------------
# Key storage (module-level, set at hub startup)
# ---------------------------------------------------------------------------

_stored_key_hash: str = ""


def set_api_key(key: str) -> None:
    """Store the SHA-256 hash of the API key. Called once at hub startup."""
    global _stored_key_hash
    _stored_key_hash = hashlib.sha256(key.encode()).hexdigest()


def verify_key(provided: str) -> bool:
    """Constant-time comparison of provided key against stored hash.

    Returns False immediately if no key has been configured.
    """
    if not _stored_key_hash or not provided:
        return False
    provided_hash = hashlib.sha256(provided.encode()).hexdigest()
    # hmac.compare_digest is constant-time for equal-length hex strings
    return hmac.compare_digest(provided_hash, _stored_key_hash)


# ---------------------------------------------------------------------------
# In-memory auth failure rate limiter
# ---------------------------------------------------------------------------


class AuthRateLimiter:
    """Sliding-window auth failure tracker.

    Tracks failed auth attempts by client IP. After max_failures failures
    within window_seconds, the IP is locked out for lockout_seconds.

    State is in-memory only — resets on hub restart.
    """

    def __init__(
        self,
        max_failures: int = 20,
        window_seconds: int = 60,
        lockout_seconds: int = 300,
    ) -> None:
        self._max_failures = max_failures
        self._window = window_seconds
        self._lockout = lockout_seconds
        # ip → deque of failure timestamps
        self._failures: dict[str, deque[float]] = {}
        # ip → lockout expiry timestamp
        self._locked: dict[str, float] = {}

    def is_locked(self, ip: str) -> bool:
        """Return True if the IP is currently in lockout."""
        expiry = self._locked.get(ip, 0.0)
        if time.monotonic() < expiry:
            return True
        # Lockout expired — clean up
        self._locked.pop(ip, None)
        return False

    def record_failure(self, ip: str) -> None:
        """Record a failed auth attempt; apply lockout if threshold exceeded."""
        now = time.monotonic()
        q = self._failures.setdefault(ip, deque())
        q.append(now)
        # Evict timestamps outside the sliding window
        cutoff = now - self._window
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self._max_failures:
            self._locked[ip] = now + self._lockout
            q.clear()
            logger.warning("Hub auth lockout applied to %s for %ds", ip, self._lockout)

    def record_success(self, ip: str) -> None:
        """Clear failure history for IP on successful auth."""
        self._failures.pop(ip, None)
        self._locked.pop(ip, None)


# Module-level limiter (configured at startup)
_rate_limiter: AuthRateLimiter = AuthRateLimiter()


def configure_rate_limiter(
    max_failures: int,
    window_seconds: int,
    lockout_seconds: int,
) -> None:
    """Reconfigure the module-level auth rate limiter. Called at hub startup."""
    global _rate_limiter
    _rate_limiter = AuthRateLimiter(max_failures, window_seconds, lockout_seconds)


def get_rate_limiter() -> AuthRateLimiter:
    """Return the module-level auth rate limiter."""
    return _rate_limiter


# ---------------------------------------------------------------------------
# FastAPI middleware
# ---------------------------------------------------------------------------


def make_auth_middleware(trust_localhost: bool):  # type: ignore[return]
    """Return a Starlette middleware callable for HTTP request authentication.

    Skips /health (always public).
    Skips trusted loopback IPs when trust_localhost=True.
    Checks Authorization: Bearer or X-InkArms-Key header.
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    class _AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):  # type: ignore[override]
            # Health check is always public
            if request.url.path == "/health":
                return await call_next(request)

            client_ip = request.client.host if request.client else ""

            # Trust localhost when configured
            if trust_localhost and client_ip in TRUSTED_IPS:
                return await call_next(request)

            # Check for lockout
            if _rate_limiter.is_locked(client_ip):
                return JSONResponse(
                    {"detail": "Too many authentication failures"},
                    status_code=429,
                )

            # Extract key from Authorization header or X-InkArms-Key
            key = _extract_http_key(request)
            if not verify_key(key):
                _rate_limiter.record_failure(client_ip)
                logger.warning("Hub auth failure from %s %s", client_ip, request.url.path)
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)

            _rate_limiter.record_success(client_ip)
            return await call_next(request)

    return _AuthMiddleware


def _extract_http_key(request: Any) -> str:  # type: ignore[name-defined]
    """Extract API key from Authorization: Bearer or X-InkArms-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return request.headers.get("X-InkArms-Key", "").strip()


# ---------------------------------------------------------------------------
# WebSocket auth helper (used in ws/chat.py)
# ---------------------------------------------------------------------------


async def ws_authenticate(ws: Any, trust_localhost: bool) -> bool:  # type: ignore[name-defined]
    """Perform first-message WebSocket authentication.

    Accepts the connection, waits up to 5 seconds for
    {"type": "auth", "token": "<key>"}, verifies the key, and sends
    {"type": "ready"} on success or closes with code 1008 on failure.

    Returns True if authentication succeeded, False otherwise.
    The connection is always accepted before this function is called —
    do NOT call ws.accept() again.
    """
    import asyncio
    import json as _json

    client_ip = ws.client.host if ws.client else ""

    # Trust localhost when configured (skip key check)
    if trust_localhost and client_ip in TRUSTED_IPS:
        await ws.send_json({"type": "ready"})
        return True

    # Check for lockout
    if _rate_limiter.is_locked(client_ip):
        await ws.send_json({"type": "error", "message": "too many failures"})
        await ws.close(code=1008)
        return False

    try:
        auth_msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
        if auth_msg.get("type") != "auth" or not verify_key(auth_msg.get("token", "")):
            _rate_limiter.record_failure(client_ip)
            logger.warning("Hub WS auth failure from %s", client_ip)
            await ws.send_json({"type": "error", "message": "unauthorized"})
            await ws.close(code=1008)
            return False
    except asyncio.TimeoutError:
        logger.warning("Hub WS auth timeout from %s", client_ip)
        await ws.close(code=1008)
        return False
    except (_json.JSONDecodeError, Exception):  # noqa: BLE001
        await ws.close(code=1008)
        return False

    _rate_limiter.record_success(client_ip)
    await ws.send_json({"type": "ready"})
    return True
