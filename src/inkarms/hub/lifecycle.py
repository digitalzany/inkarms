"""
Hub lifecycle — startup and shutdown of platform adapters and message processor.

Reuses the same bootstrap pattern as ``cli/commands/platforms.py`` but runs
inside the hub daemon instead of a foreground CLI process. Key differences:
- Uses ``warn_callback=logger.warning`` instead of Rich console.print
- Wraps each adapter listen-loop in a supervisor with exponential back-off
- Stores state on AppState for access by API handlers
- Tracks session metadata in hub.db session_index
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from inkarms.audit import get_audit_logger
from inkarms.platforms.adapters import create_adapters
from inkarms.platforms.processor import MessageProcessor
from inkarms.platforms.rate_limiter import get_rate_limiter
from inkarms.platforms.router import MessageRouter
from inkarms.platforms.session_mapper import SessionMapper
from inkarms.platforms.sessions import PlatformSessionStore

if TYPE_CHECKING:
    from inkarms.hub.app import AppState

logger = logging.getLogger(__name__)

# Supervisor settings
_MAX_RETRIES = 5
_BASE_BACKOFF = 2.0  # seconds
_RATE_LIMITER_CLEANUP_INTERVAL = 3600  # 1 hour


async def start_hub(app_state: AppState) -> None:
    """Bootstrap the hub: create adapters, processor, and router.

    Populates ``app_state.router``, ``app_state.session_store``, and
    ``app_state.processor``.  Registers adapters and starts them.
    """
    from inkarms.config.loader import get_config

    config = get_config()

    # Build adapters (warn via logger, no Rich dependency)
    adapters = create_adapters(config, warn_callback=logger.warning)

    # Shared infrastructure
    session_mapper = SessionMapper(chains=config.context.session_chains)
    session_store = PlatformSessionStore()
    processor = _make_processor(config, session_store)

    router = MessageRouter(
        max_concurrent_tasks=config.platforms.max_concurrent_sessions,
        processor=processor,
        session_mapper=session_mapper,
        rate_limiter=get_rate_limiter(
            max_tokens=config.platforms.rate_limit_per_user,
            refill_rate=1.0,
            refill_interval=60.0,
        ),
        session_store=session_store,
    )

    for adapter in adapters:
        router.register_adapter(adapter)

    # Start router (calls adapter.start() internally)
    await router.start()

    # Replace internal listen tasks with supervised versions
    await _replace_with_supervised_listeners(router, adapters)

    # Start periodic rate-limiter cleanup
    asyncio.create_task(_rate_limiter_cleanup_loop(router))

    # Audit log
    audit = get_audit_logger()
    audit.log_hub_started(host=config.hub.host, port=config.hub.port)
    for adapter in adapters:
        audit.log_platform_adapter_started(
            platform=adapter.platform_type.value,
            mode=adapter.capabilities.markdown_flavor or "unknown",
        )

    logger.info("Hub lifecycle started with %d adapter(s)", len(adapters))

    # Store on AppState
    app_state.router = router
    app_state.session_store = session_store
    app_state.processor = processor


async def stop_hub(app_state: AppState) -> None:
    """Graceful hub shutdown: save sessions and stop router."""
    import time

    from inkarms.config.loader import get_config

    config = get_config()
    start = time.monotonic()

    if app_state.router is not None:
        # Broadcast shutdown to all open WS connections (handled in ws/events.py)
        await _broadcast_shutdown()

        # Wait up to shutdown_timeout for in-flight requests
        timeout = config.hub.shutdown_timeout
        try:
            await asyncio.wait_for(_wait_for_idle(app_state.router), timeout=float(timeout))
        except asyncio.TimeoutError:
            logger.warning("Shutdown timeout (%ds) reached; forcing stop", timeout)

        await app_state.router.stop()

    audit = get_audit_logger()
    audit.log_hub_stopped(uptime_seconds=time.monotonic() - start)
    logger.info("Hub lifecycle stopped")


def _make_processor(config: Any, session_store: PlatformSessionStore) -> MessageProcessor:
    """Create a fresh MessageProcessor.

    Must be called again on SIGHUP because ``MessageProcessor.__init__``
    captures ``get_config()`` at init time — a stale processor would miss
    updated model, security rules, and budget settings.
    """
    return MessageProcessor(
        event_callback=_hub_event_callback,
        tool_approval_callback=lambda _tc, _t: config.hub.tool_approval_mode == "auto",
        session_store=session_store,
    )


def _hub_event_callback(event: Any) -> None:
    """Log agent events from hub-initiated message processing."""
    from inkarms.models.agent import EventType

    if event.event_type in (EventType.TOOL_START, EventType.TOOL_COMPLETE, EventType.TOOL_ERROR):
        logger.debug("[%s] %s: %s", event.event_type, event.tool_name, event.message)
    elif event.event_type in (EventType.ITERATION_START, EventType.AGENT_COMPLETE):
        logger.debug("[%s] %s", event.event_type, event.message)


async def _replace_with_supervised_listeners(
    router: MessageRouter, adapters: list[Any]
) -> None:
    """Cancel unsupervised listen tasks and replace with supervised versions.

    The router's ``start()`` method creates plain asyncio tasks for listening.
    We cancel those and create supervised replacements with crash-recovery.
    """
    # Cancel all existing listen tasks (they are named "listen-<platform>")
    for task in list(router._tasks):
        if task.get_name().startswith("listen-"):
            task.cancel()

    await asyncio.sleep(0)  # Let cancellations propagate

    for adapter in adapters:
        task = asyncio.create_task(
            _supervised_listen(router, adapter),
            name=f"supervised-{adapter.platform_type.value}",
        )
        router._tasks.add(task)
        task.add_done_callback(router._tasks.discard)


async def _supervised_listen(router: MessageRouter, adapter: Any) -> None:
    """Listen loop with exponential back-off on crash.

    After ``_MAX_RETRIES`` consecutive failures the adapter is marked
    unhealthy in router._adapters but the hub keeps running.
    """
    platform = adapter.platform_type.value
    for attempt in range(_MAX_RETRIES):
        try:
            await router.listen_to_adapter(adapter)
            # Clean exit (router stopped) — do not retry
            return
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.error(
                "Adapter %s crashed (attempt %d/%d): %s",
                platform,
                attempt + 1,
                _MAX_RETRIES,
                exc,
                exc_info=True,
            )
            get_audit_logger().log_platform_adapter_error(platform=platform, error=str(exc))
            if attempt < _MAX_RETRIES - 1:
                backoff = _BASE_BACKOFF ** attempt
                logger.info("Restarting %s in %.1fs…", platform, backoff)
                await asyncio.sleep(backoff)

    logger.critical("Adapter %s failed after %d attempts — marked unhealthy", platform, _MAX_RETRIES)


async def _rate_limiter_cleanup_loop(router: MessageRouter) -> None:
    """Periodically clean up stale rate-limiter buckets to prevent memory growth."""
    while True:
        try:
            await asyncio.sleep(_RATE_LIMITER_CLEANUP_INTERVAL)
            if router._rate_limiter and hasattr(router._rate_limiter, "cleanup_old_buckets"):
                await router._rate_limiter.cleanup_old_buckets()
                logger.debug("Rate-limiter cleanup complete")
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("Rate-limiter cleanup error: %s", exc)


async def _broadcast_shutdown() -> None:
    """Send {"type": "shutdown"} to all open /ws/events subscribers."""
    try:
        from inkarms.hub.ws.events import broadcast

        await broadcast({"type": "shutdown"})
    except Exception as exc:  # noqa: BLE001
        logger.debug("Shutdown broadcast skipped: %s", exc)


async def _wait_for_idle(router: MessageRouter) -> None:
    """Wait until the router has no active handle tasks."""
    while True:
        active = sum(
            1 for t in router._tasks if t.get_name().startswith("handle-")
        )
        if active == 0:
            return
        logger.debug("Waiting for %d in-flight request(s)…", active)
        await asyncio.sleep(0.5)
