"""
InkArms Hub FastAPI application.

Lifespan:
    startup  → open hub.db, init BudgetTracker, register SIGHUP handler,
               load entry-point plugins, start platform adapters (Phase 2)
    shutdown → sync budget, broadcast shutdown to WS clients, close DB

Auth middleware wraps all routes except /health.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from inkarms.hub import auth as hub_auth
from inkarms.hub import budget as hub_budget
from inkarms.hub import db as hub_db
from inkarms.hub.api import budget as budget_router
from inkarms.hub.api import cron as cron_router
from inkarms.hub.api import openai as openai_router
from inkarms.hub.api import platforms as platforms_router
from inkarms.hub.api import sessions as sessions_router
from inkarms.hub.api import status as status_router
from inkarms.hub.api import triggers as triggers_router
from inkarms.hub.ws import chat as ws_chat
from inkarms.hub.ws import events as ws_events
from inkarms.hub.ws import logs as ws_logs

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------


class AppState:
    """Mutable state attached to the FastAPI app instance."""

    router: Any = None          # MessageRouter (Phase 2)
    session_store: Any = None   # PlatformSessionStore (Phase 2)
    processor: Any = None       # MessageProcessor (Phase 2)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Hub startup and shutdown lifecycle."""
    from inkarms.config.loader import get_config
    from inkarms.hub.api.status import set_start_time
    from inkarms.storage.paths import get_hub_db_path

    cfg = get_config()

    # --- Startup ---
    set_start_time(time.monotonic())

    # Open hub.db
    await hub_db.connect(get_hub_db_path())

    # Start cron scheduler (loads jobs from hub.db)
    from inkarms.hub import scheduler as hub_scheduler
    await hub_scheduler.start(cfg)

    # Initialise BudgetTracker from DB
    await hub_budget.init(
        daily_limit=cfg.cost.budgets.daily,
        sync_interval=cfg.hub.budget_sync_interval,
    )

    # Warn about unenforceable budget limits
    if cfg.cost.budgets.weekly is not None or cfg.cost.budgets.monthly is not None:
        logger.warning(
            "hub: budgets.weekly / budgets.monthly are not enforced — "
            "only budgets.daily is supported. See Known Limitations."
        )

    # Start platform adapters if configured
    if cfg.hub.auto_start_platforms and cfg.platforms.enable:
        from inkarms.hub.lifecycle import start_hub as _start_hub
        await _start_hub(app.state.hub)

    # Register SIGHUP handler — use closure so handler has access to AppState
    hub_state = app.state.hub
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(
        signal.SIGHUP,
        lambda: asyncio.create_task(_on_sighup(hub_state)),
    )

    # Load entry-point plugins
    _load_router_plugins(app)

    logger.info("InkArms Hub started on %s:%d", cfg.hub.host, cfg.hub.port)

    yield  # --- Running ---

    # --- Shutdown ---
    logger.info("InkArms Hub shutting down…")

    # Sync budget early — flush accumulated cost before any teardown
    try:
        await hub_budget.get_budget_tracker().sync_now()
    except RuntimeError:
        pass  # Not initialised (e.g. tests)

    # Stop platform adapters (broadcasts shutdown to WS, waits for in-flight)
    if app.state.hub.router is not None:
        from inkarms.hub.lifecycle import stop_hub as _stop_hub
        await _stop_hub(app.state.hub)

    from inkarms.hub import scheduler as hub_scheduler
    await hub_scheduler.shutdown()
    # Final budget sync + close (captures any cost from in-flight requests)
    await hub_budget.shutdown()
    await hub_db.close()


async def _on_sighup(app_state: AppState) -> None:
    """Full config reload on SIGHUP.

    Sequence:
    1. Reload + validate config — abort immediately on any error (hub keeps
       running with old config, no downtime).
    2. Sync BudgetTracker to DB before adapter restart to prevent cost loss.
    3. If platform adapters are running: stop them, recreate MessageProcessor
       with new config, restart adapters.
    4. If adapters were not running but new config says start them: start them.
    """
    from inkarms.config.loader import get_config

    logger.info("SIGHUP received — reloading config…")

    # Step 1: Validate (raises on invalid YAML / schema errors)
    try:
        new_config = get_config(reload=True)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "SIGHUP: config reload failed — keeping old config (%s)", exc
        )
        return

    # Step 2: Sync budget before adapter restart
    try:
        await hub_budget.get_budget_tracker().sync_now()
    except RuntimeError:
        pass  # Budget tracker not initialised

    # Step 3 / 4: Restart adapters if needed
    from inkarms.hub.lifecycle import start_hub, stop_hub

    was_running = app_state.router is not None
    should_run = (
        new_config.hub.auto_start_platforms and new_config.platforms.enable
    )

    if was_running:
        logger.info("SIGHUP: stopping platform adapters for reload…")
        await stop_hub(app_state)
        if should_run:
            logger.info("SIGHUP: restarting platform adapters…")
            await start_hub(app_state)
    elif should_run:
        logger.info("SIGHUP: starting platform adapters (newly enabled)…")
        await start_hub(app_state)

    logger.info("SIGHUP: config reload complete")


def _load_router_plugins(app: FastAPI) -> None:
    """Mount APIRouter instances registered via inkarms.hub.routers entry points."""
    try:
        from importlib.metadata import entry_points

        for ep in entry_points(group="inkarms.hub.routers"):
            try:
                router = ep.load()
                app.include_router(router, prefix="/ext")
                logger.info("Hub plugin loaded: %s", ep.name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Hub plugin %r failed to load: %s", ep.name, exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Entry-point plugin loading skipped: %s", exc)


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the hub FastAPI application."""
    from inkarms.config.loader import get_config

    cfg = get_config()

    app = FastAPI(
        title="InkArms Hub",
        description="InkArms always-on daemon API",
        version="1.0",
        lifespan=lifespan,
        # Disable OpenAPI docs in production (optional; keep for now)
        docs_url="/docs",
        redoc_url=None,
    )

    app.state.hub = AppState()

    # Auth middleware (wraps everything except /health)
    AuthMiddleware = hub_auth.make_auth_middleware(trust_localhost=cfg.hub.trust_localhost)
    app.add_middleware(AuthMiddleware)

    # Configure auth subsystem
    hub_auth.configure_rate_limiter(
        max_failures=cfg.hub.auth_max_failures,
        window_seconds=cfg.hub.auth_window_seconds,
        lockout_seconds=cfg.hub.auth_lockout_seconds,
    )

    # Register routers
    app.include_router(status_router.router)
    app.include_router(budget_router.router)
    app.include_router(sessions_router.router)
    app.include_router(platforms_router.router)
    app.include_router(cron_router.router)
    app.include_router(triggers_router.router)
    app.include_router(openai_router.router)
    app.include_router(ws_chat.router)
    app.include_router(ws_events.router)
    app.include_router(ws_logs.router)

    return app


# Module-level app instance (used by uvicorn: inkarms.hub.app:app)
app = create_app()
