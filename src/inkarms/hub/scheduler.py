"""
Hub cron scheduler.

Wraps APScheduler v3 AsyncIOScheduler. All jobs are loaded from hub.db
on startup and re-persisted there on CRUD operations. APScheduler is used
for scheduling only — hub.db remains the source of truth.

Schedule formats accepted:
- Cron expression: "*/5 * * * *" (minute, hour, dom, month, dow)
- Interval shorthand: "every 5m", "every 1h", "every 30s"

Bash jobs run via asyncio.to_thread(sandbox.execute, command) to avoid
blocking the event loop. AI query jobs run via MessageProcessor.process().

Both job types use max_instances=1 (via APScheduler job_defaults) so that
a long-running job does not overlap with a scheduled retry.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

# APScheduler v3 imports are guarded so this module can be imported without
# the [hub] extras installed (tests may mock at the module boundary).
_scheduler: Any = None  # apscheduler.schedulers.asyncio.AsyncIOScheduler

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def start(config: Any) -> None:
    """Create and start the AsyncIOScheduler. Load saved jobs from hub.db."""
    global _scheduler

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except ImportError as exc:
        raise ImportError(
            "APScheduler is required for cron jobs. "
            "Install with: pip install inkarms[hub]"
        ) from exc

    _scheduler = AsyncIOScheduler(
        job_defaults={"max_instances": 1, "misfire_grace_time": 30},
    )
    _scheduler.start()

    # Load persisted jobs from hub.db
    await _load_jobs_from_db()
    logger.info("Scheduler started")


async def shutdown() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")


def get_scheduler() -> Any:
    """Return the running scheduler. Raises RuntimeError if not started."""
    if _scheduler is None:
        raise RuntimeError("Scheduler not started — call hub.scheduler.start() first")
    return _scheduler


# ---------------------------------------------------------------------------
# Job management (called from api/cron.py)
# ---------------------------------------------------------------------------


def add_job(job_row: dict[str, Any]) -> None:
    """Register a cron job with APScheduler from a hub.db row dict."""
    if not job_row.get("enabled", True):
        return

    scheduler = get_scheduler()
    job_id = job_row["id"]
    schedule = job_row["schedule"]
    job_type = job_row.get("type", "bash")
    command = job_row["command"]
    session_id = job_row.get("session_id", "default")

    trigger_kwargs = _parse_schedule(schedule)

    if job_type == "bash":
        func = _run_bash_job
        args = [job_id, command]
    else:
        allowed_tools = job_row.get("allowed_tools")
        func = _run_ai_query_job
        args = [job_id, command, session_id, allowed_tools]

    try:
        scheduler.add_job(
            func,
            trigger=trigger_kwargs["trigger"],
            trigger_args=trigger_kwargs["trigger_args"],
            id=job_id,
            replace_existing=True,
            args=args,
        )
        logger.debug("Scheduled job %r (%s)", job_id, schedule)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to schedule job %r: %s", job_id, exc)


def remove_job(job_id: str) -> None:
    """Unregister a job from APScheduler. Silent if not found."""
    try:
        scheduler = get_scheduler()
        scheduler.remove_job(job_id)
        logger.debug("Removed scheduled job %r", job_id)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Job runners
# ---------------------------------------------------------------------------


async def _run_bash_job(job_id: str, command: str) -> None:
    """Execute a bash cron job in a thread pool (non-blocking)."""
    from inkarms.config.loader import get_config
    from inkarms.hub import db as hub_db
    from inkarms.security.sandbox import SandboxExecutor

    logger.info("Cron job %r: running bash command", job_id)
    started = datetime.now().isoformat()
    result_str = ""

    try:
        config = get_config()
        sandbox = SandboxExecutor.from_config(config.security)
        result = await asyncio.to_thread(sandbox.execute, command)
        if result.blocked:
            result_str = f"BLOCKED: {result.blocked_reason}"
            logger.warning("Cron job %r blocked: %s", job_id, result.blocked_reason)
        elif not result.success:
            result_str = f"EXIT {result.exit_code}: {result.stderr[:500]}"
            logger.warning("Cron job %r failed (exit %s)", job_id, result.exit_code)
        else:
            result_str = result.stdout[:500]
            logger.info("Cron job %r succeeded", job_id)
    except Exception as exc:  # noqa: BLE001
        result_str = f"ERROR: {exc}"
        logger.error("Cron job %r error: %s", job_id, exc)

    await _record_run(hub_db, job_id, started, result_str)

    from inkarms.audit import get_audit_logger
    get_audit_logger().log_hub_cron_run(job_id=job_id, result=result_str[:200])


async def _run_ai_query_job(
    job_id: str,
    prompt: str,
    session_id: str,
    allowed_tools: list[str] | None,
) -> None:
    """Execute an AI query cron job via MessageProcessor.process()."""
    from inkarms.config.loader import get_config
    from inkarms.hub import db as hub_db
    from inkarms.platforms.processor import MessageProcessor
    from inkarms.platforms.sessions import PlatformSessionStore

    logger.info("Cron job %r: running AI query", job_id)
    started = datetime.now().isoformat()
    result_str = ""

    try:
        config = get_config()
        session_store = PlatformSessionStore()
        processor = MessageProcessor(
            tool_approval_callback=lambda _tc, _t: (
                config.hub.cron_tool_approval_mode == "auto"
            ),
            session_store=session_store,
        )
        response = await processor.process(
            query=prompt,
            session_id=session_id,
        )
        result_str = response.content[:500] if response.content else "(empty)"
        logger.info("Cron job %r AI query completed", job_id)
    except Exception as exc:  # noqa: BLE001
        result_str = f"ERROR: {exc}"
        logger.error("Cron job %r AI error: %s", job_id, exc)

    await _record_run(hub_db, job_id, started, result_str)

    from inkarms.audit import get_audit_logger
    get_audit_logger().log_hub_cron_run(job_id=job_id, result=result_str[:200])


async def _record_run(hub_db: Any, job_id: str, started_at: str, result: str) -> None:
    """Update last_run, last_result, and run_count in hub.db."""
    try:
        await hub_db.execute(
            """
            UPDATE cron_jobs
            SET last_run = ?, last_result = ?, run_count = run_count + 1
            WHERE id = ?
            """,
            (started_at, result, job_id),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to record cron job %r run: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Schedule parsing
# ---------------------------------------------------------------------------

_INTERVAL_PATTERN = re.compile(r"^every\s+(\d+)\s*(s|m|h|d)$", re.IGNORECASE)
_UNIT_MAP = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def _parse_schedule(schedule: str) -> dict[str, Any]:
    """Parse a schedule string into APScheduler trigger kwargs.

    Returns a dict with keys 'trigger' (str) and 'trigger_args' (dict).
    """
    schedule = schedule.strip()

    # "every 5m", "every 1h", "every 30s"
    m = _INTERVAL_PATTERN.match(schedule)
    if m:
        value = int(m.group(1))
        unit = _UNIT_MAP[m.group(2).lower()]
        return {"trigger": "interval", "trigger_args": {unit: value}}

    # Standard cron expression (5 or 6 fields)
    parts = schedule.split()
    if len(parts) in (5, 6):
        field_names = ["minute", "hour", "day", "month", "day_of_week"]
        if len(parts) == 6:
            field_names = ["second"] + field_names
        return {
            "trigger": "cron",
            "trigger_args": dict(zip(field_names, parts)),
        }

    raise ValueError(
        f"Unrecognised schedule format: {schedule!r}. "
        "Use a cron expression (e.g. '0 * * * *') or interval (e.g. 'every 5m')."
    )


# ---------------------------------------------------------------------------
# DB bootstrap
# ---------------------------------------------------------------------------


async def _load_jobs_from_db() -> None:
    """Load all enabled cron jobs from hub.db and register them."""
    try:
        from inkarms.hub import db as hub_db

        rows = await hub_db.execute_fetchall(
            "SELECT * FROM cron_jobs WHERE enabled = 1"
        )
        for row in rows:
            add_job(dict(row))
        logger.info("Loaded %d cron job(s) from hub.db", len(rows))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load cron jobs from DB: %s", exc)
