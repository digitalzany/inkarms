"""
Hub SQLite database (hub.db).

Single aiosqlite connection protected by an asyncio.Lock. WAL mode provides
concurrent readers and a single writer without locking readers out.

Schema:
    schema_version  — migration tracking
    session_index   — hub session metadata (fast REST queries)
    cron_jobs       — persistent scheduled job definitions
    daily_cost      — daily cost accumulator for BudgetTracker

Do NOT use this module for conversation turns; those live in JSON daily files
under ~/.inkarms/memory/platform/<session_id>/daily/.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level connection state
# ---------------------------------------------------------------------------

_conn: Any = None  # aiosqlite.Connection
_lock: asyncio.Lock = asyncio.Lock()
_checkpoint_task: asyncio.Task[None] | None = None


def is_connected() -> bool:
    """Return True when hub.db is open (hub is running)."""
    return _conn is not None

# ---------------------------------------------------------------------------
# Schema SQL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_index (
    session_id       TEXT PRIMARY KEY,
    platform         TEXT NOT NULL,
    platform_user_id TEXT,
    channel_id       TEXT,
    display_name     TEXT,
    created_at       TEXT NOT NULL,
    last_active      TEXT NOT NULL,
    turn_count       INTEGER DEFAULT 0,
    total_tokens     INTEGER DEFAULT 0,
    total_cost       REAL    DEFAULT 0.0,
    primary_model    TEXT
);

CREATE INDEX IF NOT EXISTS session_idx_platform
    ON session_index(platform);

CREATE INDEX IF NOT EXISTS session_idx_last_active
    ON session_index(last_active);

CREATE TABLE IF NOT EXISTS cron_jobs (
    id          TEXT PRIMARY KEY,
    schedule    TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'bash',
    command     TEXT NOT NULL,
    session_id  TEXT NOT NULL DEFAULT 'default',
    notify      TEXT,
    enabled     INTEGER NOT NULL DEFAULT 1,
    last_run    TEXT,
    last_result TEXT,
    run_count   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS daily_cost (
    date       TEXT PRIMARY KEY,
    total_cost REAL NOT NULL DEFAULT 0.0
);
"""

# Future schema migrations (applied in order, starting at version 2).
MIGRATIONS: list[str] = []

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def connect(db_path: Path) -> None:
    """Open hub.db, apply PRAGMA settings, create schema, run migrations."""
    global _conn, _checkpoint_task

    try:
        import aiosqlite
    except ImportError as exc:
        raise ImportError(
            "aiosqlite is required for the hub. "
            "Install with: pip install inkarms[hub]"
        ) from exc

    db_path.parent.mkdir(parents=True, exist_ok=True)
    _conn = await aiosqlite.connect(str(db_path))
    _conn.row_factory = aiosqlite.Row

    async with _lock:
        # Performance + safety pragmas
        await _conn.execute("PRAGMA journal_mode=WAL")
        await _conn.execute("PRAGMA synchronous=NORMAL")
        await _conn.execute("PRAGMA busy_timeout=5000")

        # Create schema if not present
        await _conn.executescript(_SCHEMA_SQL)

        # Seed schema_version row 1 if missing
        row = await (await _conn.execute("SELECT MAX(version) FROM schema_version")).fetchone()
        current_version: int = row[0] or 0
        if current_version == 0:
            await _conn.execute(
                "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES(1, ?)",
                (datetime.now().isoformat(),),
            )

        await _run_migrations(current_version)
        await _conn.commit()

    # Start WAL checkpoint background task
    _checkpoint_task = asyncio.create_task(_wal_checkpoint_loop())
    logger.debug("hub.db opened at %s", db_path)


async def close() -> None:
    """Flush pending writes and close hub.db."""
    global _conn, _checkpoint_task

    if _checkpoint_task is not None:
        _checkpoint_task.cancel()
        _checkpoint_task = None

    if _conn is not None:
        async with _lock:
            await _conn.commit()
            await _conn.close()
        _conn = None
        logger.debug("hub.db closed")


async def execute(sql: str, params: tuple[Any, ...] = ()) -> Any:
    """Execute a write statement under the lock."""
    async with _lock:
        cursor = await _conn.execute(sql, params)
        await _conn.commit()
        return cursor


async def execute_fetchone(sql: str, params: tuple[Any, ...] = ()) -> Any:
    """Execute a read statement and return the first row."""
    async with _lock:
        cursor = await _conn.execute(sql, params)
        return await cursor.fetchone()


async def execute_fetchall(sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    """Execute a read statement and return all rows."""
    async with _lock:
        cursor = await _conn.execute(sql, params)
        return await cursor.fetchall()


# ---------------------------------------------------------------------------
# Session index helpers
# ---------------------------------------------------------------------------


async def upsert_session(
    *,
    session_id: str,
    platform: str,
    platform_user_id: str | None = None,
    channel_id: str | None = None,
    display_name: str | None = None,
    turn_count_delta: int = 0,
    tokens_delta: int = 0,
    cost_delta: float = 0.0,
    primary_model: str | None = None,
) -> None:
    """Insert or update a session_index row."""
    now = datetime.now().isoformat()
    async with _lock:
        existing = await (
            await _conn.execute(
                "SELECT turn_count, total_tokens, total_cost FROM session_index WHERE session_id = ?",
                (session_id,),
            )
        ).fetchone()

        if existing is None:
            await _conn.execute(
                """
                INSERT INTO session_index
                    (session_id, platform, platform_user_id, channel_id, display_name,
                     created_at, last_active, turn_count, total_tokens, total_cost, primary_model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    platform,
                    platform_user_id,
                    channel_id,
                    display_name,
                    now,
                    now,
                    turn_count_delta,
                    tokens_delta,
                    cost_delta,
                    primary_model,
                ),
            )
        else:
            await _conn.execute(
                """
                UPDATE session_index SET
                    last_active      = ?,
                    turn_count       = turn_count + ?,
                    total_tokens     = total_tokens + ?,
                    total_cost       = total_cost + ?,
                    primary_model    = COALESCE(?, primary_model),
                    display_name     = COALESCE(?, display_name),
                    channel_id       = COALESCE(?, channel_id)
                WHERE session_id = ?
                """,
                (
                    now,
                    turn_count_delta,
                    tokens_delta,
                    cost_delta,
                    primary_model,
                    display_name,
                    channel_id,
                    session_id,
                ),
            )
        await _conn.commit()


async def delete_session(session_id: str) -> bool:
    """Remove a session from session_index. Returns True if a row was deleted."""
    async with _lock:
        cursor = await _conn.execute(
            "DELETE FROM session_index WHERE session_id = ?", (session_id,)
        )
        await _conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Daily cost helpers
# ---------------------------------------------------------------------------


async def read_daily_cost(date: str) -> float:
    """Read today's accumulated cost from the DB."""
    row = await execute_fetchone(
        "SELECT total_cost FROM daily_cost WHERE date = ?", (date,)
    )
    return float(row["total_cost"]) if row else 0.0


async def upsert_daily_cost(date: str, cost: float) -> None:
    """Persist today's accumulated cost to the DB."""
    await execute(
        "INSERT INTO daily_cost(date, total_cost) VALUES(?, ?) "
        "ON CONFLICT(date) DO UPDATE SET total_cost = ?",
        (date, cost, cost),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _run_migrations(current_version: int) -> None:
    """Apply any pending schema migrations in order."""
    for i, sql in enumerate(MIGRATIONS, start=2):
        if i > current_version:
            await _conn.execute(sql)
            await _conn.execute(
                "INSERT INTO schema_version(version, applied_at) VALUES(?, ?)",
                (i, datetime.now().isoformat()),
            )
    await _conn.commit()


async def _wal_checkpoint_loop() -> None:
    """Run PRAGMA wal_checkpoint(PASSIVE) every 5 minutes to bound WAL size."""
    while True:
        try:
            await asyncio.sleep(300)
            async with _lock:
                await _conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                logger.debug("WAL checkpoint complete")
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("WAL checkpoint failed: %s", exc)
